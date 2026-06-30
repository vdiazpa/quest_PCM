#RH_utils.py


from egret.models.unit_commitment import _solve_unit_commitment, create_tight_unit_commitment_model, _save_uc_results
from egret.model_library.unit_commitment.uc_model_generator import generate_model, UCFormulation
from egret.model_library.unit_commitment.uc_utils import SlackType
from egret.model_library.defn import BasePointType
from egret.common.log import logger as egret_logger
from pcm.data_manager.data_main import DataManager
from pcm.market_manager.market_main import MarketSimulator
import egret.common.lazy_ptdf_utils as lpu
import egret.data.ptdf_utils as ptdf_utils
from collections import namedtuple
from copy import deepcopy
import networkx as nx
import logging
from pyomo.environ import *
import time 

bar = "################################################################"


def RH_windows_fixes(T, F, L):
    #Gets window lengths and fixed time periods given L, F, and T
    W = F + L
    t = 1
    windows = []
    fixes = []

    t_star = T - W + 1
    while t <= T:
        r = T - t + 1
        H = min(W, r)
        s_e = list(range(t, t + H))
        windows.append(s_e)

        w_o = (t + W - 1 > T)
        w_s = (t < t_star) and (t + min(F, H) > t_star)

        if (t < t_star) and (w_o or w_s):
            F_k = min(F, t_star - t, H)
        else:
            F_k = min(F, H)

        if t >= t_star:
            fixes.append((t, t + H - 1))
            t += H
        else:
            fixes.append((t, t + F_k - 1))
            t += F_k

    return windows, fixes

def slice_md(md_full, s_e):
    """
    Slice a ModelData object to a subset of time periods.
    s_e: list of time periods in window (ints), e.g. [1,2,3,4,5].
    md_full: Egret ModelData instance for full planning horizon.
    """
    md = deepcopy(md_full)

    #1 Update system time_keys as strings
    md.data["system"]["time_keys"] = [str(t) for t in s_e]              # OJO: Need to fix abt type consistency

    #2 Slice load data 
    elems = md.data["elements"]
    if "load" in elems:
        for _, ldict in elems["load"].items():
            p_load_dict = ldict.get("p_load", None)
            if isinstance(p_load_dict, dict) and p_load_dict.get("data_type") == "time_series":
                vals = p_load_dict["values"]
                new_vals = [vals[t-1] for t in s_e]
                p_load_dict["values"] = new_vals
                #print(f"Load {bus} p_load after slicing: {p_load_dict['values']}")
    else:
        print("Warning: 'load' not found in elements")

    #3 Slice renewable generator data 
    if "generator" in elems:
        for _, gdict in elems["generator"].items():
            if gdict.get("generator_type") == "renewable":
                for attr in ("p_min", "p_max"):
                    pdict = gdict.get(attr, None)
                    if isinstance(pdict, dict) and pdict.get("data_type") == "time_series":
                        vals = pdict["values"]
                        new_vals = [vals[t-1] for t in s_e]
                        pdict["values"] = new_vals
                #print(f"Gen {gen} p_min after slicing: {gdict['p_min'].get('values', None)}")
    else:
        print("Warning: 'generator' not found in elements")

    return md

def apply_init_state_to_md(md, init_states):

    generators = md.data["elements"].get("generator", {})
    for gen in generators.keys():
        if generators[gen].get("generator_type") == "thermal":
            generators[gen]["initial_status"] = init_states['StatusAtT0'].get(gen, 0)
            generators[gen]["initial_p_output"] = init_states['PowerGeneratedT0'].get(gen, 0)
    return md

def extract_init_state_and_fixed_from_model(model, t_roll_local, md_wind, fix_vars=True):
    """
    Returns:
      InitialState: dict for next window carryover
      fixed_vars:   dict of variable values for times <= t_roll_local (optional)
    """

    # Egret models often have time keys as strings ("1","2",...)
    samp_t = next(iter(model.TimePeriods))

    def tkey(t_int):
        return str(t_int) if isinstance(samp_t, str) else t_int

    t0 = int(value(model.InitialTime))
    tr = int(t_roll_local)

    # StatusAtT0 taken from md_wind 
    StatusAtT0 = {g: md_wind.data['elements']['generator'][g].get('initial_status', 0)for g in model.ThermalGenerators}

    # --- compute status streak through t_roll_local ---
    last_status = {g: int(value(model.UnitOn[g, tkey(tr)])) for g in model.ThermalGenerators}
    status_change = {g: False for g in model.ThermalGenerators}

    status_dict = {}
    for g in model.ThermalGenerators:
        for t in range(t0, tr + 1):
            if t == t0:
                if value(model.UnitOn[g, tkey(t)]) - value(model.UnitOnT0[g]) != 0:
                    status_change[g] = True
                    break
            else:
                if value(model.UnitOn[g, tkey(t)]) - value(model.UnitOn[g, tkey(t-1)]) != 0:
                    status_change[g] = True
                    break

        if not status_change[g]:
            if int(value(model.UnitOnT0[g])) == 1:
                status_dict[g] = int(StatusAtT0[g]) + (tr - t0 + 1)
            else:
                status_dict[g] = int(StatusAtT0[g]) - (tr - t0 + 1)
        else:
            streak = 1
            for t in range(tr - 1, t0 - 1, -1):
                if int(value(model.UnitOn[g, tkey(t)])) == last_status[g]:
                    streak += 1
                else:
                    break
            status_dict[g] = streak if last_status[g] == 1 else -streak

    #  InitialState carryover 
    InitialState = { "PowerGeneratedT0": {g: value(model.PowerGenerated[g, tkey(tr)]) for g in model.ThermalGenerators}, "StatusAtT0": status_dict}

    # If storage exists in the model, include it 
    if hasattr(model, "StorageUnits") and hasattr(model, "SoC"):
        InitialState["SoCT0"] = {b: value(model.SoC[b, tkey(tr)]) for b in model.StorageUnits}

    #  Fixed solution slice up to roll/fix time 
    fixed_vars = None
    if fix_vars:
        fixed_vars = {}

        times = list(range(t0, tr + 1))

        # thermal UC vars
        if hasattr(model, "UnitOn"):
            fixed_vars["UnitOn"] = {(g, t): int(round(value(model.UnitOn[g, tkey(t)])))for g in model.ThermalGenerators for t in times}
        if hasattr(model, "UnitStart"):
            fixed_vars["UnitStart"] = {(g, t): int(round(value(model.UnitStart[g, tkey(t)])))for g in model.ThermalGenerators for t in times}
        if hasattr(model, "UnitStop"):
            fixed_vars["UnitStop"] = {(g, t): int(round(value(model.UnitStop[g, tkey(t)])))for g in model.ThermalGenerators for t in times}

        #storage (if present)
        if hasattr(model, "StorageUnits"):
            if hasattr(model, "IsCharging"):
                fixed_vars["IsCharging"] = {(b, t): int(round(value(model.IsCharging[b, tkey(t)]))) for b in model.StorageUnits for t in times}
            if hasattr(model, "IsDischarging"):
                fixed_vars["IsDischarging"] = {(b, t): int(round(value(model.IsDischarging[b, tkey(t)]))) for b in model.StorageUnits for t in times}


    return InitialState, fixed_vars

def save_solution_to_csv(fixed_sol):
    import csv
    all_t = sorted({t for (g,t) in fixed_sol['UnitOn'].keys()})
    all_g = sorted({g for (g,t) in fixed_sol['UnitOn'].keys()})

    with open(f"RH_solution.csv", mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Variable", "Unit"] + all_t)

        for g in all_g:
            row = ["UnitOn", g]
            for t in all_t:
                row.append(fixed_sol['UnitOn'].get((g,t), ""))
            writer.writerow(row)

        for g in all_g:
            row = ["UnitStart", g]
            for t in all_t:
                row.append(fixed_sol['UnitStart'].get((g,t), ""))
            writer.writerow(row)

        for g in all_g:
            row = ["UnitStop", g]
            for t in all_t:
                row.append(fixed_sol['UnitStop'].get((g,t), ""))
            writer.writerow(row)

def build_ptdf_dict(md):

    ptdf_options = lpu.populate_default_ptdf_options(None)
    baseMVA = md.data.get("system", {}).get("baseMVA", 100.0)
    lpu.check_and_scale_ptdf_options(ptdf_options, baseMVA)

    elems = md.data["elements"]

    PTDF  = ptdf_utils.VirtualPTDFMatrix(
        branches=elems["branch"],
        buses= elems["bus"],
        reference_bus=md.data.get("system", {}).get( "reference_bus",next(iter(elems["bus"]))),
        base_point=BasePointType.FLATSTART,
        ptdf_options=ptdf_options,
        interfaces=elems.get("interface", None), 
        contingencies=elems.get("contingency", None))

    return ptdf_options,  {"": PTDF}

def load_fixed_sol(model, fixed_sol=None): 

    t_sample = next(iter(model.TimePeriods))
    #print("Eval model TimePeriods element type:", type(t_sample), "example:", t_sample)

    model.fix_sol_constraint = ConstraintList(doc = "Fix_Vars_from_RH_Sol")
    print("Fixing stitched solution to model...")
    for (g,t), val in fixed_sol["UnitOn"].items():
        #model.UnitOn[g,t].fix(int(round(val)))
        model.fix_sol_constraint.add(expr = model.UnitOn[g,t] == int(round(val)))
    for (g,t), val in fixed_sol["UnitStart"].items():
        #model.UnitStart[g,t].fix(int(round(val)))
        model.fix_sol_constraint.add(expr = model.UnitStart[g,t] == int(round(val)))
    for (g,t), val in fixed_sol["UnitStop"].items():
        #model.UnitStop[g,t].fix(int(round(val)))
        model.fix_sol_constraint.add(expr = model.UnitStop[g,t] == int(round(val)))

    return  model

def write_state_comparison_csv(init_states, md_window, model, filename="state_check.csv"):
    import csv

    with open(filename, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Generator",
            "Computed_StatusAtT0",
            "MD_initial_status",
            "Model_UnitOnT0",
            "Model_UnitOnT0State"
        ])

        for g in model.ThermalGenerators:
            computed = init_states["StatusAtT0"].get(g, None)
            md_stat  = md_window.data["elements"]["generator"][g].get("initial_status", None)

            unit_on_t0 = None
            unit_on_t0_state = None

            if hasattr(model, "UnitOnT0"):
                unit_on_t0 = int(round(value(model.UnitOnT0[g])))

            if hasattr(model, "UnitOnT0State"):
                unit_on_t0_state = value(model.UnitOnT0State[g])

            writer.writerow([g,computed,md_stat,unit_on_t0,unit_on_t0_state])

    print(f"\nState comparison written to {filename}\n")

def add_branch_contingencies(md, max_cont=None):
    branches = md.data["elements"]["branch"]

    G = nx.Graph()

    for br, data in branches.items():
        if data.get("in_service", True):
            G.add_edge(data["from_bus"], data["to_bus"], name=br )

    bridge_branches = set()
    for u, v in nx.bridges(G):
        bridge_branches.add(G[u][v]["name"])

    print("Removing islanding contingency branches:")
    print(sorted(bridge_branches))

    conts = {}
    for k, br in enumerate(branches):
        if max_cont is not None and len(conts) >= max_cont:
            break

        if not branches[br].get("in_service", True):
            continue

        if br in bridge_branches:
            continue

        conts[f"cont_{br}"] = { "branch_contingency": br }
    md.data["elements"]["contingency"] = conts
    print(f"Added {len(conts)} non-islanding branch contingencies")

    return md

def run_RH_egret(md_full, F, L, RH_opt_gap=0.01, bench_gap=0.01, tee=False, write_csv=False):

    #========================================================================================== Initialization
    ptdf_options, PTDF_cache = build_ptdf_dict(md_full)

    init_states    = None
    windows, fixes = RH_windows_fixes(len(md_full.data['system']['time_keys']), F, L)
    fixed_sol      = {"UnitOn": {}, "UnitStart": {}, "UnitStop": {} ,"IsCharging": {}, "IsDischarging": {}} #,"ChargePower": {}, "DischargePower": {}, "SoC": {} }
    UCFormulation  = namedtuple('UCFormulation', ['status_vars','power_vars','reserve_vars','generation_limits','ramping_limits','production_costs','uptime_downtime','startup_costs','network_constraints' ] )
    form_list      =  ['garver_3bin_vars', 'garver_power_vars','garver_power_avail_vars', 'pan_guan_gentile_KOW_generation_limits','damcikurt_ramping', 'KOW_production_costs_tightened', 'rajan_takriti_UT_DT', 'KOW_startup_costs', 'ptdf_power_flow'] # 
    formulation    = UCFormulation(*form_list)

    #for code profiling
    slice_time = 0.0
    build_time = 0.0
    rh_solve_time = 0.0
    t_dispatch_build = 0.0
    t_dispatch_solve = 0.0

    egret_logger.setLevel(logging.ERROR)
    main_data_path = "Data/RTS_GMLC"
    yaml_path = "config/GMLC_config.yaml"

    input_manager = DataManager(main_data_path, yaml_path)
    input_manager.export_input_json()

    simulator = MarketSimulator(input_manager)
    simulator.create_DA_RT_models()

    md_full = simulator.DA_model

    md_full["current_market"] = "DA"

    #============================================================================================ Main RH loop
    for i, (window, fix_periods) in enumerate(zip(windows, fixes)):
        t_fix0, t_fix1 = fix_periods

        t_slice = time.perf_counter()
        md_window = slice_md(md_full, window)
        slice_time += time.perf_counter() - t_slice

        print(f"\nWindow {i+1}/{len(windows)}: {window} | fix {fix_periods}")

        #============================================== Apply initial state if i>0
        if init_states is not None:
            md_window = apply_init_state_to_md(md_window, init_states)
        
        #=============================================== Generate model for current window
        t_build = time.perf_counter()
        model = simulator.egret_uc_model_generator(md_window)
        # model   = generate_model(md_window, uc_formulation=formulation, relax_binaries=False, slack_type=SlackType.BUS_BALANCE, PTDF_matrix_dict=PTDF_cache, ptdf_options=ptdf_options) 
        build_time += time.perf_counter() - t_build

        # # Sanity check for injections; save comparison of computed initial status vs. model init status
        # if i==1: 
        #     write_state_comparison_csv(init_states, md_window, model, filename="initial_state_comparison.csv")

        #model.write(f"RH_window_{i+1}_model.lp", io_options={"symbolic_solver_labels": True})

        #============================================== Solve
        t_rh_solve = time.perf_counter()
        _solve_unit_commitment(model, solver='gurobi', mipgap=RH_opt_gap, timelimit=None, solver_tee=False, symbolic_solver_labels=False, solver_options = None, solve_method_options=None, relaxed=False)
        rh_solve_time += time.perf_counter() - t_rh_solve

        t_roll_local = window.index(t_fix1) + 1  # local index of t_fix1 in the window (1..len(window))
        init_states, fixed_vars = extract_init_state_and_fixed_from_model(model, t_roll_local, md_window, fix_vars=True)

        #=============================================== Stitch solution
        for k, vardict in fixed_vars.items():
            if k not in fixed_sol:
                continue
            for (idx, t_local), v in vardict.items():
                t_global = window[t_local - 1]     # convert local -> global
                if t_fix0 <= t_global <= t_fix1:
                    fixed_sol[k][(idx, t_global)] = v

    if write_csv:
        save_solution_to_csv(fixed_sol)
    
    #=================================================================Evaluate stitched solution 
    print(f"\n{bar}", "\nSolving fixed-commitment dispatch...", f"\n{bar}")

    t_dispatch_build = time.perf_counter()
    md_dispatch = deepcopy(md_full)
    md_dispatch.data["elements"].pop("contingency", None)  # remove contingencies for dispatch solve

    model = generate_model(md_dispatch, uc_formulation=formulation, 
        relax_binaries=True, slack_type=SlackType.BUS_BALANCE,PTDF_matrix_dict=PTDF_cache, ptdf_options=ptdf_options)
    t_dispatch_build = time.perf_counter() - t_dispatch_build

    model.dual=Suffix(direction=Suffix.IMPORT)

    model = load_fixed_sol(model, fixed_sol)

    t_dispatch_solve = time.perf_counter()
    _solve_unit_commitment(
        model, solver='gurobi', 
        mipgap=bench_gap, timelimit=None, solver_tee=tee, symbolic_solver_labels=False, 
        solver_options=None, solve_method_options=None, relaxed=True)
    t_dispatch_solve = time.perf_counter() - t_dispatch_solve
    
    print("RH Objective:", round(value(list(model.component_data_objects(Objective, active=True))[0]),2))
    print(f"{bar}", "\nRH solution complete", f"\n{bar}")

    return model, None, fixed_sol, {"slice_time": slice_time, "build_time": build_time, "rh_solve_time": rh_solve_time, "t_dispatch_build": t_dispatch_build, "t_dispatch_solve": t_dispatch_solve}

def run_monolithic_egret(md_full, mipgap=0.01, tee=False):

    t0 = time.perf_counter()
    ptdf_options, PTDF_cache = build_ptdf_dict(md_full)

    UCFormulationNT = namedtuple(
        'UCFormulation',
        [ 'status_vars', 'power_vars', 'reserve_vars',
            'generation_limits', 'ramping_limits', 'production_costs',
            'uptime_downtime', 'startup_costs', 'network_constraints' ])

    formulation = UCFormulationNT(
        'garver_3bin_vars', 'garver_power_vars', 'garver_power_avail_vars',  'pan_guan_gentile_KOW_generation_limits', 'damcikurt_ramping',
        'KOW_production_costs_tightened', 'rajan_takriti_UT_DT', 'KOW_startup_costs', 'ptdf_power_flow' )


    model = generate_model(
        md_full,
        uc_formulation=formulation,
        relax_binaries=False,
        slack_type=SlackType.BUS_BALANCE,
        PTDF_matrix_dict=PTDF_cache,
        ptdf_options=ptdf_options)

    build_done = time.perf_counter()

    _solve_unit_commitment(
        model,
        solver='gurobi',
        mipgap=mipgap,
        timelimit=None,
        solver_tee=tee,
        symbolic_solver_labels=False,
        solver_options=None,
        solve_method_options=None,
        relaxed=False,
    )

    solve_done = time.perf_counter()

    results = _save_uc_results(model, relaxed=False).data
    obj = results["system"]["total_cost"]

    return model, {
        "method": "MONO","F": "", "L": "", 
        "build_time": build_done - t0, "solve_time": solve_done - build_done, "total_time": solve_done - t0,
        "objective": obj}


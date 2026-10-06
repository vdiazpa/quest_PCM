
from pyomo.environ import Objective, value
from egret.common.log import logger as egret_logger
from pcm.data_manager.data_main import DataManager
from pcm.market_manager.market_main import MarketSimulator
from pcm.result_manager.result_main import ResultManager
import networkx as nx
import pandas as pd
from RH_utils import run_RH_egret
import logging
import time
egret_logger.setLevel(logging.ERROR)


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

#_____________________________________________/Read data & create a simulator object.

# main_data_path = "Data/duke_revised"
main_data_path = "Data/RTS_GMLC"

yaml_path = "config/GMLC_config.yaml"
input_manager = DataManager(main_data_path, yaml_path)
input_manager.export_input_json()
simulator = MarketSimulator(input_manager)
simulator.create_DA_RT_models()

#_____________________________________________/Extract DA model data from simulator.

t_rh_start = time.perf_counter()

md_full = simulator.DA_model.clone()
md_full.data["current_market"] = "DA"
md_full.data["system"]["timestamp"] = [f"{hour-1:02d}:00" for hour in input_manager.DA_periods]
# md_full.write("questPCM_DA_model.json")

# for g, gd in md_full.data["elements"]["generator"].items():
#     if gd.get("generator_type") in ["thermal", "Thermal"]:
#         if gd.get("startup_fuel") == []:
#             gd.pop("startup_fuel")


#_____________________________________________/Run RH and time it. 
# rh_mod, _, fixed_sol, times = run_RH_egret(md_full, F=4, L=6, simulator=simulator, RH_opt_gap=0.01, lazy_ptdf=False, cache_ptdf=True, relax_lookahead=True)
# t_rh_end  = time.perf_counter()

# #convert solved RH to Egret md
# rh_md = simulator.egret_uc_result_exporter(rh_mod, relaxed=False)
# # rh_md = rh_md.clone_at_time_indices(list(range(24)))

# #put RH result where 's ResultManager expects DA 
# current_day = (input_manager.start_date + pd.Timedelta(days=0)).date()
# simulator.DA_result_dict = {current_day: rh_md}

# simulator.data_obj.config["simulate_DA_only"] = True

# #Generate results for RH solution
# result_processor = ResultManager(simulator, "Results")
# result_processor.export_results()


# rh_time = t_rh_end - t_rh_start 
# print("RH windows solve (secs):", round(rh_time,4))

# #_____________________________________________/Create DA model and solve with lazy PTDF. Time. 
t0 = time.perf_counter()
da_lazy_mod = simulator.egret_uc_model_generator(md_full, ptdf_options={"lazy": True})   # pyomo model with quest storage constraints0
# da_mod.write("questPCM_DA_model_new.lp", io_options={"symbolic_solver_labels": True})
t1 = time.perf_counter()     #build time


pyomo_sol, _, _ = simulator.egret_uc_solver(
    da_lazy_mod, 
    solver="gurobi",
    mipgap=input_manager.config.get("mipgap", 0.01), 
    timelimit=None, 
    solver_tee=False, 
    symbolic_solver_labels=False, 
    solver_options=None, 
    solve_method_options=None, 
    relaxed=False)

t2 = time.perf_counter() 

lazy_mono_obj = value(next(da_lazy_mod.component_data_objects(Objective, active=True)))
# da_mod.write("questPCM_DA_model_after_solve.lp", io_options={"symbolic_solver_labels": True}) #c heck in LP if transmission constraints were added. 


# ____________/ Get QuESt outputs
# # Convert solved lazy Pyomo model -> Egret ModelData
# lazy_md = simulator.egret_uc_result_exporter(da_lazy_mod, relaxed=False)

# # Keep first 24 hours 
# # lazy_md = lazy_md.clone_at_time_indices(list(range(24)))

# # Put result where QuESt expects DA results
# current_day = (input_manager.start_date + pd.Timedelta(days=0)).date()

# simulator.DA_result_dict = {current_day: lazy_md}

# # DA-only outputs
# simulator.data_obj.config["simulate_DA_only"] = True
# # simulator.data_obj.config["solve_pricing_problem"] = False

# # Export plots/results
# lazy_results = ResultManager(simulator, "Results_lazy")
# lazy_results.export_results()

# ____________/ Print LAZY results

build_time = t1-t0
solve_time = t2-t1

print("\n====================LAZY PTDF===========================")
print("MONO OBJECTIVE:", lazy_mono_obj)
print("MONO BUILD TIME (secs):", round(build_time,4))
print("MONO SOLVE TIME (secs):", round(solve_time,4))


# #___________________________________________________/ Monolithic DA model with non-lazy PTDF. Time.


da_mod_mono = simulator.egret_uc_model_generator(md_full, ptdf_options={"lazy": False})   # pyomo model with quest storage constraints0
# # da_mod.write("questPCM_DA_model_new.lp", io_options={"symbolic_solver_labels": True})

t3 = time.perf_counter()

pyomo_sol, _, _ = simulator.egret_uc_solver(
    da_mod_mono, 
    solver="gurobi",
    mipgap=0.00, 
    timelimit=None, 
    solver_tee=False, 
    symbolic_solver_labels=False, 
    solver_options=None, 
    solve_method_options=None, 
    relaxed=False)

t4 = time.perf_counter() - t3

mono_obj = value(next(da_mod_mono.component_data_objects(Objective, active=True)))

print("\n====================Original Monolithic===========================")
print("MONO OBJECTIVE:", mono_obj)
print("MONO SOLVE TIME (secs):", round(t4,4))


# # da_mod = simulator.egret_uc_model_generator(md)
# # 

# # simulator.simulate_market() 1

# # result_path = "Results/"
# # result_processor = ResultManager(simulator, result_path)
# # result_processor.export_results()

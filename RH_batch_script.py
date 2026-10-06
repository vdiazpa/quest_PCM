from pyomo.environ import Objective, value
from egret.common.log import logger as egret_logger
from pcm.data_manager.data_main import DataManager
from pcm.market_manager.market_main import MarketSimulator
import pandas as pd
from RH_utils import run_RH_egret
from datetime import datetime
import logging
import time
egret_logger.setLevel(logging.ERROR)


#_____________________________________________/Read data & create a simulator object.

# main_data_path = "Data/duke_revised"
main_data_path = "Data/RTS_GMLC"

yaml_path = "config/GMLC_config.yaml"
input_manager = DataManager(main_data_path, yaml_path)
input_manager.export_input_json()
simulator = MarketSimulator(input_manager)
simulator.create_DA_RT_models()

simulation_st_date = input_manager.config.get("start_date", "N/A")
simulation_end_date = input_manager.config.get("end_date", "N/A")

#==================================-Experimental Parameters

FandLs     = [(4,12)]
relax_look = [True, False]
opt_gaps   = [0.01, 0.001]

#===================================-Clone DA model 

md_full = simulator.DA_model.clone()
md_full.data["current_market"] = "DA"

# ===================== Non-lazy monolithic =====================

t0 = time.perf_counter()
da_mod_mono = simulator.egret_uc_model_generator(md_full,ptdf_options={"lazy": False}) # input_manager.config.get("mipgap", 0.001),
t1 = time.perf_counter()
mod_sol, _, _ = simulator.egret_uc_solver(da_mod_mono,solver="gurobi",mipgap=0.00,timelimit=None,solver_tee=False,symbolic_solver_labels=False,solver_options=None,solve_method_options=None,relaxed=False)
t2 = time.perf_counter()

mono_obj = value(next(da_mod_mono.component_data_objects(Objective, active=True)))

mono_build = t1 - t0
mono_solve = t2 - t1
mono_total = t2 - t0


# ===================== Experiments =====================

rows = []

for g in opt_gaps:

    #===========Lazy PTDF============
    t0 = time.perf_counter()
    lazy_mod = simulator.egret_uc_model_generator(md_full,ptdf_options={"lazy": True})
    t1 = time.perf_counter()

    p_sol, _, _ = simulator.egret_uc_solver(lazy_mod,solver="gurobi",mipgap=g,timelimit=None,solver_tee=False,symbolic_solver_labels=False,solver_options=None,solve_method_options=None,relaxed=False)
    t2 = time.perf_counter()
    lazy_obj   = value(next(lazy_mod.component_data_objects(Objective, active=True)))

    lazy_build = t1 - t0
    lazy_solve = t2 - t1
    lazy_total = t2 - t0


    #============RH===================
    for F, L in FandLs:
        for r in relax_look:
            t0 = time.perf_counter()
            rh_mod, _, rh_sol, res = run_RH_egret(md_full,F=F,L=L,simulator=simulator,RH_opt_gap=g,lazy_ptdf=False,cache_ptdf=True,relax_lookahead=r)
            t1 = time.perf_counter()
            rh_total = t1 - t0

            rows.append({
                "F": F,
                "L": L,
                "relax_lookahead": r,
                "opt_gap": g,
                "RH_total_time": rh_total,
                "RH_objective": res["rh_objective"],
                "rh_build_time": res["rh_build_time"],
                "rh_solve_time": res["rh_solve_time"],
                "rh_dispatch_build": res["t_dispatch_build"],
                "rh_dispatch_solve": res["t_dispatch_solve"],
                "lazy_build_time": lazy_build,
                "lazy_solve_time": lazy_solve,
                "lazy_total_time": lazy_total,
                "lazy_objective": lazy_obj,
                "mono_build_time": mono_build,
                "mono_solve_time": mono_solve,
                "mono_total_time": mono_total,
                "mono_objective": mono_obj,
                "RH_gap_pct": 100 * (res["rh_objective"] - mono_obj) / mono_obj,
                "lazy_gap_pct": 100 * (lazy_obj - mono_obj) / mono_obj, 
                "sim_st_date": simulation_st_date, 
                "sim_end_date": simulation_end_date,
                })

#===============Save outputs
df = pd.DataFrame(rows)
df.to_csv("RH_benchmark_results_0.01_only.csv", index=False)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
df.to_csv(f"RH_benchmark_results_{stamp}.csv", index=False)
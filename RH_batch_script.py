from pyomo.environ import Objective, value
from egret.common.log import logger as egret_logger
from pcm.data_manager.data_main import DataManager
from pcm.market_manager.market_main import MarketSimulator
import networkx as nx
from RH_utils import run_RH_egret
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

#==================================-Experimental Parameters

FandLs     = [(4,6), (8,4), (8,6), (12,6)]
relax_look = [True, False]
opt_gaps   = [0.01, 0.001]

#===================================-Clone DA model 

md_full = simulator.DA_model.clone()
md_full.data["current_market"] = "DA"

#==================================Build and solve non-lazy mono & solve to 0% optimality gap. Time it.
t0 = time.perf_counter()
da_mod_mono = simulator.egret_uc_model_generator(md_full, ptdf_options={"lazy": False})   # pyomo model with quest storage constraints0

t_mono_st     = time.perf_counter()
mod_sol, _, _ = simulator.egret_uc_solver(da_mod_mono, solver="gurobi",mipgap=0.00,  timelimit=None, solver_tee=False, symbolic_solver_labels=False, solver_options=None, solve_method_options=None, relaxed=False)
t_mono_end    = time.perf_counter() - t_mono_st #solve time monolithic
mono_obj      = value(next(da_mod_mono.component_data_objects(Objective, active=True)))

#===================================Experiments Loop

rows = []

for g in opt_gaps: 

    #============================================Build & solve DA w. lazy PTDF algorithm. Time it.
    t_lazy_st0   = time.perf_counter() 
    lazy_mod    = simulator.egret_uc_model_generator(md_full, ptdf_options={"lazy": True})  
    t_lazy_st   = time.perf_counter()  

    p_sol, _, _ = simulator.egret_uc_solver(lazy_mod, solver="gurobi", mipgap=g, timelimit=None, solver_tee=False, symbolic_solver_labels=False, solver_options=None, solve_method_options=None, relaxed=False)
    lazy_obj    = value(next(lazy_mod.component_data_objects(Objective, active=True)))
    t_lazy_end  = time.perf_counter()   

    t_lazy  = t_lazy_end - t_lazy_st0

    for t in FandLs: 
        for r in relax_look:
            F, L = t
            t_rh_start = time.perf_counter() 
            rh_mod, _, rh_sol, res = run_RH_egret(md_full, F=F, L=L, simulator=simulator, RH_opt_gap=g, lazy_ptdf=False, cache_ptdf=True, relax_lookahead=r)
            t_rh_end   = time.perf_counter()
            rh_time    = t_rh_end - t_rh_start 
            print(f"F={F}, L={L}, relax_lookahead={r}, RH_opt_gap={g}, RH windows solve (secs): {round(rh_time,4)}")
            rows.append({
                "F": F, 
                "L": L, 
                "relax_lookahead": r, 
                "opt_gap": g, 
                "RH_total_time": rh_time, 
                "RH_objective": res["rh_objective"], 
                "lazy_solve_time": t_lazy, 
                "lazy_build_time": t_lazy_st-t_lazy_st0,
                "lazy_time": t_lazy,
                "lazy_objective": lazy_obj, 
                "mono_build_time": t0-t_mono_st,
                "mono_solve_time": t_mono_st-t_mono_end,
                "mono_objective": mono_obj, 
                "rh_build_time": res["rh_build_time"], 
                "rh_solve_time": res["rh_solve_time"], 
                "rh_dispatch_build": res["t_dispatch_build"], 
                "rh_dispatch_solve": res["t_dispatch_solve"]})




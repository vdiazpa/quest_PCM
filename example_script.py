
from pyomo.environ import Objective, value
from egret.common.log import logger as egret_logger
from pcm.data_manager.data_main import DataManager
from pcm.market_manager.market_main import MarketSimulator
# from RH_utils import *
import logging
import time
egret_logger.setLevel(logging.ERROR)


#_____________________________________________/Create a simulator object]
main_data_path = "Data/RTS_GMLC"
yaml_path = "config/GMLC_config.yaml"
input_manager = DataManager(main_data_path, yaml_path)
input_manager.export_input_json()
simulator = MarketSimulator(input_manager)
simulator.create_DA_RT_models()

#_____________________________________________/Extract DA model data (egret) from simulator]


from RH_utils import run_RH_egret

md_full = simulator.DA_model.clone()
md_full.data["current_market"] = "DA"

t_rh_start = time.perf_counter()
rh_mod, _, fixed_sol, times = run_RH_egret(md_full, F=8, L=8, simulator=simulator, RH_opt_gap=0.001)
t_rh_end  = time.perf_counter()

#_____________________________________________/Create pyomo model with DA model data. Time. Write LP]
t0 = time.perf_counter()
da_mod = simulator.egret_uc_model_generator(md_full)   # pyomo model with quest storage constraints
da_mod.write("questPCM_DA_model.lp", io_options={"symbolic_solver_labels": True})
t1 = time.perf_counter()     #build time

#_____________________________________________/Solve pyomo model]

pyomo_sol, _, _ = simulator.egret_uc_solver(
    da_mod, 
    solver="gurobi",
    mipgap=input_manager.config.get("mipgap", 0.001), 
    timelimit=None, 
    solver_tee=False, 
    symbolic_solver_labels=False, 
    solver_options=None, 
    solve_method_options=None, 
    relaxed=False)

t2 = time.perf_counter() 

mono_obj = value(next(da_mod.component_data_objects(Objective, active=True)))
da_mod.write("questPCM_DA_model_after_solve.lp", io_options={"symbolic_solver_labels": True}) #c heck in LP if transmission constraints were added. 

#=============== Print mono results

build_time = t1-t0
solve_time = t2-t1
rh_time = t_rh_end - t_rh_start 

print("MONO OBJECTIVE:", mono_obj)
print("MONO BUILD TIME (secs):", round(build_time,4))
print("MONO SOLVE TIME (secs):", round(solve_time,4))
print("RH windows solve (secs):", round(rh_time,4))



# da_mod = simulator.egret_uc_model_generator(md)
# 

# simulator.simulate_market() 1

# result_path = "Results/"
# result_processor = ResultManager(simulator, result_path)
# result_processor.export_results()

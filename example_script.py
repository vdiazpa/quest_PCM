import logging
import os
from egret.common.log import logger as egret_logger
from pcm.data_manager.data_main import DataManager
from pcm.market_manager.market_main import MarketSimulator
from pcm.result_manager.result_main import ResultManager# %%
from egret.data.model_data import ModelData
from RH_utils import *
import csv 

egret_logger.setLevel(logging.ERROR)
main_data_path = "Data/RTS_GMLC"
yaml_path = "config/GMLC_config.yaml"

input_manager = DataManager(main_data_path, yaml_path)
input_manager.export_input_json()

simulator = MarketSimulator(input_manager)
simulator.create_DA_RT_models()

md_full = simulator.DA_model.clone()
md_full.data["current_market"] = "DA"

rh_mod, _, fixed_sol, times = run_RH_egret(
    md_full, F=12, L=12, 
    model_generator = simulator.egret_uc_model_generator, 
    uc_solver = simulator.uc_solver)


# da_mod = simulator.egret_uc_model_generator(md)
# da_mod.write("questPCM_DA_model.lp", io_options={"symbolic_solver_labels": True})

# simulator.simulate_market() 1

# result_path = "Results/"
# result_processor = ResultManager(simulator, result_path)
# result_processor.export_results()

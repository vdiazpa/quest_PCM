#run_experiment_hpc.py

from pyomo.environ import Objective, value
from egret.common.log import logger as egret_logger
from pcm.data_manager.data_main import DataManager
from pcm.market_manager.market_main import MarketSimulator
import pandas as pd
from RH_utils import run_RH, save_solution_to_csv
import logging
import time
import argparse
import json
from pathlib import Path
egret_logger.setLevel(logging.ERROR)

#dir with this script
BENCHMARK_DIR = Path(__file__).resolve().parent #quest_pcm/RH_benchmark/

# QuESt PCM root dir
PROJECT_ROOT  = BENCHMARK_DIR.parent

#Experiment files and output dirs
MANIFEST_PATH = BENCHMARK_DIR / "experiment_manifest.csv"
RUNS_DIR      = BENCHMARK_DIR / "runs"

#QuESt PCM data and config
DATA_DIR   = PROJECT_ROOT / "Data"
CONFIG_DIR = PROJECT_ROOT / "config"


def build_run_config(run_id, manifest): 

    # Get run specs from experiment manifest

    run = manifest.loc[manifest["run_id"] == run_id].iloc[0] # extracts experiment row as a series
    
    config = { 
    
      "run_id" : run_id, 
      "system" : run["system"],
      
      "simulation_start" : run["start_date"],
      "horizon_length"   : run["horizon_length"],
      "solve_method"     : run["solve_method"],
      }
      
      if run["solve_method"] == "RH":
      
        config["(F,L)"]   = (run["F"], run["L"]),
        config["relax_l"] = run["relax_l"],
      
      config["mipgap"] = run["mipgap"], 
      config["seed"]   = run["seed"], 
      
      return config
    

def run_quest_default(md_full, simulator, mipgap, seed, 
        run_dir=None, # directory to save lazy  (quest default solve algorithm)
        ): 

    t0 = time.perf_counter()
    model = simulator.egret_uc_model_generator(md_full, ptdf_options={"lazy": True}) 
    t1 = time.perf_counter()

    build_time  = t1 - t0

    # Solve
    mod_sol, _, _ = simulator.egret_uc_solver(
        model, 
        solver="gurobi", 
        mipgap=mipgap, 
        timelimit=None,
        solver_tee=False, 
        symbolic_solver_labels=False,
        solver_options={"Seed": seed},
        solve_method_options=None,
        relaxed=False)

    obj_val = value(next(model.component_data_objects(Objective, active=True)))

    t2 = time.perf_counter()
    solve_time = t2 - t1

    return {"OFV": obj_val, "build_time": build_time, "solve_time": solve_time, "t_dispatch_build": None, "t_dispatch_solve": None}


def run_rolling_horizon(md_full, F, L, simulator, RH_opt_gap=0.01, relax_lookahead=False, seed=None, run_dir=None):

    rh_mod, _, fixed_sol, res = run_RH(
        md_full, F=F, L=L, simulator=simulator, RH_opt_gap=RH_opt_gap, solver_options = {"Seed": seed}, lazy_ptdf=False, cache_ptdf=True, relax_lookahead=relax_lookahead)

    #save stitched RH binaries
    save_solution_to_csv(fixed_sol, run_dir / "outputs" / "RH_solution.csv")
    
    return {
        "OFV": res["rh_objective"], 
        "build_time": res["rh_build_time"], 
        "solve_time": res["rh_solve_time"], 
        "t_dispatch_build": res["t_dispatch_build"], 
        "t_dispatch_solve": res["t_dispatch_solve"]}


def execute_experiment(run, md_full, simulator, run_dir):

    method = run["solve_method"] # get solve method, mipgap and seed from the run configuration (matrix row)
    mipgap = run["mipgap"]
    seed = int(run["seed"])

    if method == "LAZY":
        results = run_quest_default(md_full, simulator, mipgap, seed)

    elif method == "RH":
        results = run_rolling_horizon(
            md_full, 
            F=int(run["F"]), L=int(run["L"]), simulator=simulator, 
            RH_opt_gap=mipgap, 
            seed=seed,
            relax_lookahead=bool(run["relax_l"]), 
            run_dir=run_dir)

    return results


def extract_quest_commitment(result_md): 
    fixed_sol = 1 ## TO DO

def main(): 

    # Read command-line arguments

    parser = argparse.ArgumentParser()
    parser.add_argument("--run_id", required=True)

    args = parser.parse_args()

    run_id = args.run_id

    #===== Read manifest (CSV with all runs)

    manifest = pd.read_csv(MANIFEST_PATH, dtype={"run_id": str})

    run    = manifest.loc[manifest["run_id"] == run_id].iloc[0] # extracts experiment row as a series
    system = run["system"]


    #create run directory if it doesn't exist
    run_dir = RUNS_DIR /  run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    outputs = run_dir / "outputs"

    # Prepare ru-specific config 
    run_config = build_run_config(run_id, manifest)
    with open(run_dir / "config.json", "w") as f:
      json.dump(run_config, f, indent=4)

    #initialize QuESt
    input_manager = DataManager(str(DATA_DIR / system), str(CONFIG_DIR / "GMLC_config.yaml"))
    input_manager.export_input_json()

    simulator = MarketSimulator(input_manager)
    simulator.create_DA_RT_models()

    #clone DA model
    
    md_full = simulator.DA_model.clone()
    md_full.data["current_market"] = "DA"

    #execute experiemnt
    results = execute_experiment(run, md_full, simulator, run_dir)

if __name__ == "__main__":
    main()





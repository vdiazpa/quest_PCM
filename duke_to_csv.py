#duke_loader.py

""" Will create RTS style csv files for QuESt PCM from Duke data. """

import pandas as pd
import os

folder_with_data = "duke_revised" #path to folder with raw duke data files.

#----------------------Create branch csv for QuESt PCM

line_data = pd.read_csv(os.path.join(folder_with_data, "line_params_new.csv"))

#Need: Line ID,From Bus,To Bus,R,X,B,Cont Rating,LTE Rating,STE Rating,Tr Ratio

rows = []
for i, row in line_data.iterrows():
    line_id     = row["line"]
    from_bus    = row["line"].split("_n")[0]
    to_bus      = "n" + row["line"].split("_n")[1]
    X           = row["reactance"]/(row["voltage_class"]**2) # ohms -> pu.
    cont_rating = row["limit"]
    Tr_ratio    = 0
    rows.append({ "Line ID": line_id, "From Bus": from_bus, " To Bus": to_bus, "X": X, "Cont Rating": cont_rating,  "LTE Rating": cont_rating, "STE Rating": cont_rating, "Tr_ratio": Tr_ratio })

line_df = pd.DataFrame(rows)
line_df.to_csv(os.path.join(folder_with_data, "branch.csv"), index=False)

#----------------------Create bus csv for QuESt PCM

# Need: Bus ID,Bus Name,BaseKV,Bus Type,MW Load,MVAR Load,Area

line_to_bus = pd.read_csv(os.path.join(folder_with_data, "line_to_bus.csv"))
load_data   = pd.read_csv(os.path.join(folder_with_data, "data_load_2023.csv"))

bus_mw   = load_data.iloc[0].to_dict()
buses_id = line_to_bus.iloc[:,1:].columns.to_list()
bus_name = [ "Bus " + bus for bus in buses_id ]
bus_type = ["PQ" if i in bus_mw else "PV" for i in buses_id]
area     = ["DUK"]*len(buses_id)

load_mw_list = []
for bus in buses_id:
    if bus in bus_mw:
        load_mw_list.append(bus_mw[bus])
    else:
        load_mw_list.append(0)

bus_df = pd.DataFrame({ "Bus ID": buses_id, "Bus Name": bus_name, "Bus Type": bus_type,"MW Load": load_mw_list, "Area": area})
bus_df.to_csv(os.path.join(folder_with_data, "bus.csv"), index=False)

#----------------------Create gen csv for QuESt PCM

# Need: GEN UID,Bus ID,Gen ID, Type, Unit Type, Category, Fuel, 
# Initial Power MW, Initial Time Hr,PMax MW,PMin MW,Min Down Time Hr,Min Up Time Hr,
# Ramp Rate MW/Min,Start Time Cold Hr,Start Time Warm Hr,Start Time Hot Hr,Start Heat Cold MBTU,
# Start Heat Warm MBTU,Start Heat Hot MBTU,Non Fuel Start Cost $,Shutdown Cost $,Fuel Price $/MMBTU,
# Output_pct_0,Output_pct_1,Output_pct_2,Output_pct_3,HR_avg_0,HR_incr_1,HR_incr_2,HR_incr_3,
# Fast start,AGC capable,Reg offer $/MW/hr,Pmax AGC MW,Pmin AGC MW,Spin offer MW,Spin offer $/MW/hr,
# NonSpin offer MW,NonSpin offer $/MW/hr,Supp offer MW,Supp offer $/MW/hr

# Type is QuESt modeling type. Renewable = curtailable, Fixed Reneable = Non-curtailable. 
# Have: name,typ,node,maxcap,actual_cap,heat_rate,mincap,var_om,no_load,st_cost,ramp,minup,mindn,kind

gen_data = pd.read_csv(os.path.join(folder_with_data, "data_genparams_partial_Interim_P1.csv"))

gen_uid = gen_data["name"].to_list()
gen_data["node"] = gen_data["node"].apply(lambda x: "n_" + str(x))

print(gen_data.head())

gens_per_bus = {}                  # num of generators per bus, to create unique gen IDs.
for i, row in gen_data.iterrows():
    bus_id = row["node"]
    if bus_id not in gens_per_bus:
        gens_per_bus[bus_id] = 1
    else:
        gens_per_bus[bus_id] += 1

gen_data["Gen ID"] = gen_data["node"].map(gens_per_bus)

def _get_unit_type(typ):
    if typ in ["coal", "ngct", "ngcc", "oil", "nuclear"]:
        return "Thermal"
    else:                    #["solar", "wind", "hydro"]:
        return "Renewable"

gen_data["Type"] = gen_data["typ"].apply(_get_unit_type)

ramp_rate = gen_data["ramp"].apply(lambda x: x/60) # MW/hr -> MW/min
p_min = gen_data["mincap"]
p_max = gen_data["actual_cap"]
mut = gen_data["minup"]
mdt = gen_data["mindn"]

gen_data["Initial Time Hr"] = -gen_data["mindn"].clip(lower=1)
gen_data["Fuel Price $/MMBTU"] = 1.0
gen_data["Initial Power MW"]   = 0.0

pct0 = p_min/p_max
pct1 = pct0 + (1-pct0)/3
pct2 = pct0 + 2 * (1-pct0) / 3
pct3 = 1.0

gen_data["Output_pct_0"] = pct0
gen_data["Output_pct_1"] = pct1  
gen_data["Output_pct_2"] = pct2
gen_data["Output_pct_3"] = pct3

gen_data["HR_avg_0"] = (1000 * (gen_data["no_load"] + gen_data["var_om"] * p_min) / p_min)
gen_data["HR_incr_1"] = 1000 *  gen_data["var_om"] 
gen_data["HR_incr_2"] = 1000 *  gen_data["var_om"] 
gen_data["HR_incr_3"] = 1000 *  gen_data["var_om"] 


gen_df = pd.DataFrame({ 
    "GEN UID": gen_uid, 
    "Bus ID":  gen_data["node"], 
    "Gen ID":  gen_data["Gen ID"], 
    "Type":    gen_data["Type"], 
    "PMax MW": p_max, 
    "PMin MW": p_min, 
    "Ramp Rate MW/Min": round(ramp_rate,4), 
    "Min Up Time Hr": mut, 
    "Min Down Time Hr": mdt, 
    "HR_avg_0": gen_data["HR_avg_0"], 
    "HR_incr_1": gen_data["HR_incr_1"], 
    "HR_incr_2": gen_data["HR_incr_2"], 
    "HR_incr_3": gen_data["HR_incr_3"], 
    "Output_pct_0": gen_data["Output_pct_0"], 
    "Output_pct_1": gen_data["Output_pct_1"], 
    "Output_pct_2": gen_data["Output_pct_2"], 
    "Output_pct_3": gen_data["Output_pct_3"],
    "Initial Time Hr": gen_data["Initial Time Hr"], 
    "Fuel Price $/MMBTU": gen_data["Fuel Price $/MMBTU"],
    "Initial Power MW": gen_data["Initial Power MW"] , 
        })

gen_df.to_csv(os.path.join(folder_with_data, "gen.csv"), index=False)
#duke_loader.py

""" Will create RTS style csv files for QuESt PCM from Duke data. """

import pandas as pd
import os

folder_with_data = "duke_revised" #path to folder with raw duke data files.

#----------------------Create branch csv for QuESt PCM

line_data = pd.read_csv(os.path.join(folder_with_data, "line_params_new.csv"))

#Line ID,From Bus,To Bus,R,X,B,Cont Rating,LTE Rating,STE Rating,Tr Ratio

rows = []
for i, row in line_data.iterrows():
    line_id     = row["line"]
    from_bus    = row["line"].split("_n")[0]
    to_bus      = "n" + row["line"].split("_n")[1]
    X           = row["reactance"]/(row["voltage_class"]**2) # ohms -> pu.
    cont_rating = row["limit"]
    Tr_ratio    = 0
    rows.append({ "Line ID": line_id, "From Bus": from_bus, "To Bus": to_bus, "X": X, "Cont Rating": cont_rating,  "LTE Rating": cont_rating, "STE Rating": cont_rating, "Tr ratio": Tr_ratio })

line_df = pd.DataFrame(rows)
line_df.to_csv(os.path.join(folder_with_data, "branch.csv"), index=False)

#----------------------Create bus csv for QuESt PCM

# Bus ID,Bus Name,BaseKV,Bus Type,MW Load,MVAR Load,Area

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

# GEN UID,Bus ID,Gen ID, Type, Unit Type, Category, Fuel, 
# Initial Power MW, Initial Time Hr,PMax MW,PMin MW,Min Down Time Hr,Min Up Time Hr,
# Ramp Rate MW/Min,Start Time Cold Hr,Start Time Warm Hr,Start Time Hot Hr,Start Heat Cold MBTU,
# Start Heat Warm MBTU,Start Heat Hot MBTU,Non Fuel Start Cost $,Shutdown Cost $,Fuel Price $/MMBTU,
# Output_pct_0,Output_pct_1,Output_pct_2,Output_pct_3,HR_avg_0,HR_incr_1,HR_incr_2,HR_incr_3,
# Fast start,AGC capable,Reg offer $/MW/hr,Pmax AGC MW,Pmin AGC MW,Spin offer MW,Spin offer $/MW/hr,
# NonSpin offer MW,NonSpin offer $/MW/hr,Supp offer MW,Supp offer $/MW/hr
# Type is QuESt modeling type. Renewable = curtailable, Fixed Reneable = Non-curtailable. 

gen_data = pd.read_csv(os.path.join(folder_with_data, "data_genparams_partial_Interim_P1.csv"))

gen_uid = gen_data["name"].to_list()
gen_data["node"] = gen_data["node"].apply(lambda x: "n_" + str(x))

# print(gen_data.head())


def _get_unit_type(typ):
    if typ in ["coal", "ngct", "ngcc", "oil", "nuclear"]:
        return "Thermal"
    elif typ in ["solar", "wind", "hydro"]:
        return "Renewable"
    else:                    
        "Unknown type row"

gen_data["Type"] = gen_data["typ"].apply(_get_unit_type)

ramp_rate = gen_data["ramp"].apply(lambda x: x/60) # MW/hr -> MW/min
p_min = gen_data["mincap"]
p_max = gen_data["actual_cap"]
mut = gen_data["minup"]
mdt = gen_data["mindn"]
gen_data["Fuel Price $/MMBTU"] = 1.0
gen_data["Initial Power MW"]   = 0.0
gen_data["Initial Time Hr"]    = -gen_data["mindn"].clip(lower=1)


pct0 = p_min/p_max
pct1 = pct0 + (1-pct0) / 3
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
    "Type":    gen_data["Type"], 
    "PMax MW": p_max, 
    "PMin MW": p_min, 
    "Ramp Rate MW/Min": round(ramp_rate,4), 
    "Min Up Time Hr":   mut, 
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
    "Non Fuel Start Cost $": gen_data["st_cost"]
        })

gen_df.to_csv(os.path.join(folder_with_data, "gen.csv"), index=False)


#----------------------Create storage CSV for QuESt PCM

sto_data = pd.read_csv(os.path.join(folder_with_data, "data_batparams_Interim_P1.csv"))

# Storage ID,Bus ID,In Service,Rated Power MW,Rated Capacity MWh,Capacity Retention Rate,Conversion Efficiency,Battery Discharging Cost $/MWh,Initial SoC,Minimum SoC,Maximum SoC

sto_id = sto_data["name"]
sto_data["node_bat"] = sto_data["node_bat"].apply(lambda x: "n_" + str(x))

bat_df = pd.DataFrame({
    "Storage ID":sto_id,
    "Bus ID" : sto_data["node_bat"], 
    "Rated Power MW": sto_data["bat_RoC"],
    "Rated Capacity MWh": sto_data["bat_cap"],
    "Conversion Efficiency": sto_data["bat_eff"],
    "Capacity Retention Rate": 1.0,                #assumed
    "Battery Discharging Cost $/MWh": 0.0,         #assumed
    "Initial SoC": 0.5,                            #assumed
    "Maximum SoC": 1.0,                            #assumed
    "Minimum SoC": 0.0,                            #assumed
    })


bat_df.to_csv(os.path.join(folder_with_data, "battery_storage.csv"), index=False)

#-------------------- Create Renwables CSV for QuESt PCM

# Year,Month,Day,Period,212_CSP_1,122_HYDRO_1,122_HYDRO_2,122_HYDRO_3,122_HYDRO_4,122_HYDRO_5,122

solar_data = pd.read_csv(os.path.join(folder_with_data, "data_solar_2023.csv"), index_col=0)
hydro_data = pd.read_csv(os.path.join(folder_with_data, "data_hydro_H.csv"))
wind_data  = pd.read_csv(os.path.join(folder_with_data, "data_wind_2023.csv"), index_col=0)

renewable_data = pd.concat([solar_data, hydro_data, wind_data], axis=1)

dates = pd.date_range(start="2023-01-01 00:00:00", periods=len(renewable_data), freq="h")

renewable_data.insert(0, "Period", dates.hour + 1)
renewable_data.insert(0, "Day", dates.day)
renewable_data.insert(0, "Month", dates.month)
renewable_data.insert(0, "Year", dates.year)

# print(renewable_data.head())

renewable_data.to_csv(os.path.join(folder_with_data, "renewable_timeseries_DA.csv"), index=False)


#-------------------- Create load CSV for QuESt PCM


load_data = pd.read_csv(os.path.join(folder_with_data, "data_load_2023.csv"), index_col=0)

dates = pd.date_range(start="2023-01-01 00:00:00", periods=len(load_data), freq="h")

load_data.insert(0, "Period", dates.hour + 1)
load_data.insert(0, "Day", dates.day)
load_data.insert(0, "Month", dates.month)
load_data.insert(0, "Year", dates.year)

# print(load_data.head())

load_data.to_csv(os.path.join(folder_with_data, "load_timeseries_DA.csv"), index=False)


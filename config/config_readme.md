# Guidance on Setting the Simulation Parameters

QuESt PCM uses .yaml configuration files to set up simulation cases. Users can define a wide range of input parameters, including optimization solver settings, simulation time configurations, and ancillary service provisions. The settings specified in the configuration files are used to selectively extract data from the input .csv files. The required parameters are as follows:

 | Parameter    | Comments                   |
|--------|-----------------------------|
|`solver`| Use this parameter to specify optimization solver for the simulation. Some popular commercial solvers include `cplex` and `gurobi`, while some open-source solvers such as `glpk`, `cbc`, `appsi_highs` can also be used. We recommend commercial solvers for large systems.
|`baseMVA`| Base MVA for the system (typical values include 100.0 and 1000.0).
|`start_date`| Start date for your simulation in MM/DD/YYYY format.
|`end_date`| End date for your simulation in MM/DD/YYYY format. Note: if you are using lookaheads, do not include last day (12/31/yyyy) as the end date.
|`DA_lookahead_periods`| Specify how many hours to lookahead in day-ahead security-constrained unit commitment (DA-SCUC) in hours.
|`simulate_DA_only`| Boolean variable to only run the day-ahead SCUC and skip the real-time SCED.
|`RT_resolution`| Duration of each real-time security-constrianed (RT-SCED) economic dispatch interval in minutes (e.g., 60 = hourly).
|`RT_lookahead_periods`| Number of future intervals (of RT_resolution length). Note: make sure its smaller than DA_lookahead_periods.
|`run_RTSCED_as`| Users have two options: `LP` or `MILP`. Linear programming (LP) is faster (as all commitment variables from DA are fixed) but mixed-integer LP (MILP) gives better commitment decisions and allows real-time scheduling of fast generators.
|`solve_pricing_problem`| Boolean variable to solve the pricing problem after solving the unit commitment and economic dispatch problems. Setting this to False will speed up the simulation but will not generate locational marginal prices (LMPs), generator revenues, and other price signals.
|`mipgap`| MIP gap for the DA-SCUC and MILP-type RT-SCED. Note: recommended values are 0.001 for small systems and 0.01 for large systems. 
|`branch_contingency`| Use this boolean variable to impose N-1 transmission security constraints. Note: this setting significantly affects computation times.
|`load_timeseries_aggregation_level`| Indicate how your load data is arranged columnwise in `load_timeseries_DA` and `load_timeseries_RT` csv files. Choices are: `node` and `area`. 
|`System Reserve`| Select `None`, `fixed`, `percentage`, or `timeseries` for power reserve you want to allocate in DA SCUC to account for uncertainty in RT-SCED. See the `reserves\` section in [data_readme](../Data/data_readme.md) for details on the three options.
|`Regulation Up`| Select `None`, `fixed`, `percentage`, or `timeseries` for upward regulation you want in the system.
|`Regulation Down`|  Select `None`, `fixed`, `percentage`, or `timeseries` for downward regulation you want in the system.
|`Spinning Reserve`|  Select `None`, `fixed`, `percentage`, or `timeseries` for 10 minute spinning reserve you want in the system.
|`NonSpinning Reserve`|  Select `None`, `fixed`, `percentage`, or `timeseries` for 10 minute non-spinning reserve you want in the system.
|`Supplemental Reserve`| Select `None`, `fixed`, `percentage`, or `timeseries` for 30 minute supplemental reserve you want in the system.
|`Flexible Ramp Up`| Select `None`, `fixed`, `percentage`, or `timeseries` for upward flexible ramping you want in the system.
|`Flexible Ramp Up`| Select `None`, `fixed`, `percentage`, or `timeseries` for downward flexible ramping you want in the system.
|`storage_AS_participation_level`| Indicates how many ancillary services can ESS participate in one time-period. Can be set between 0 and 4. 
|`evaluate_degradation`| If set to True, evaluates potential cyclic degradation of battery storage systems.
|`output_interval`| Select the output resolution for plots and JSON file exports. Available options are: `at_once`, `daily`, `weekly`, or `monthly`.
|`plotly_plots`| Boolean variable to enable HTML plot generation for enhanced visualization. Note: this may increase overall simulation time.
|`plot_ancillary_services`| Boolean variable indicating whether to generate plots for ancillary services dispatch or not.
|`plot_storage_details`| Boolean variable to generate detailed plots for each storage (SoC, costs, revenue, etc.)


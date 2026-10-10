================================================================================
HSB Living Lab - Household Water Consumption Dataset
================================================================================

Title:      Household Water Consumption Patterns Revealed Through High-Resolution
            Fixture-Level Monitoring in a Swedish Living Lab

Authors:    Jesper Knutsson
            Water Environment Technology, Architecture and Civil Engineering,
            Chalmers University of Technology, SE-41296 Gothenburg, Sweden

Contact:    jesper.knutsson@gmail.com

License:    Creative Commons Attribution 4.0 International (CC BY 4.0)


DESCRIPTION
--------------------------------------------------------------------------------
This dataset contains anonymized, fixture-level household water consumption
measurements from the HSB Living Lab (Habitation Lab), a purpose-built
residential research facility located on the Chalmers University campus in
Gothenburg, Sweden. The building comprises 28 apartments across 9 residential
clusters, monitored by 214 pulse-counting water meters (1 L resolution,
10-minute reporting intervals) covering 5 fixture types: toilets, kitchen taps,
washbasins, showers, and dishwashers/washing machines.

The cleaned dataset spans December 2019 to January 2023 (946 days with valid
data, 83.9% temporal coverage) and contains 652,315 consumption records
totalling 3,271 m3 of water.


CONTENTS
--------------------------------------------------------------------------------
HSB_Living_Lab_Water_Consumption_Anonymized.csv
    The anonymized dataset (semicolon-delimited). Contains timestamped,
    fixture-level water consumption records with anonymized apartment,
    cluster, sensor, and room identifiers. See DATA_DICTIONARY.txt for
    full column definitions.

DATA_DICTIONARY.txt
    Comprehensive data dictionary describing all columns, data types,
    anonymization methods, privacy considerations, and usage guidelines.

scripts/anonymize_data.py
    Python script used to clean and anonymize the raw sensor data.
    Documents the full data processing pipeline: Swedish-to-English
    translation, outlier removal (0.3 m3 threshold), zero-value filtering,
    identifier anonymization, and temporal feature extraction.

scripts/water_analysis.py
    Python script for statistical analysis and figure generation.
    Reproduces the descriptive statistics, non-parametric tests,
    and visualizations presented in the manuscript.

scripts/generate_figures.py
    Python script that generates all 17 publication figures from the
    anonymized dataset. Uses matplotlib with academic styling.


REQUIREMENTS
--------------------------------------------------------------------------------
Python 3.8 or higher with the following packages:
    - pandas >= 1.0.0
    - numpy >= 1.18.0
    - matplotlib >= 3.0.0
    - scipy >= 1.4.0

Install via: pip install pandas numpy matplotlib scipy


CITATION
--------------------------------------------------------------------------------
If you use this dataset, please cite:

    Knutsson, J. (2026). Household water consumption patterns revealed through
    high-resolution fixture-level monitoring in a Swedish living lab. Journal
    of Cleaner Production. [DOI pending]


ACKNOWLEDGEMENTS
--------------------------------------------------------------------------------
This work was funded by the Climate Knowledge and Innovation Community
(Climate-KIC) of the European Institute of Innovation and Technology (EIT).
The HSB Living Lab is a joint research platform established by HSB, Chalmers
University of Technology, and the University of Gothenburg, with support from
Vinnova and the Formas Research Council.

================================================================================

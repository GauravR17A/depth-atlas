Attributes {
  time {
    String _CoordinateAxisType "Time";
    Float64 actual_range 3.681936e+8, 1.7327088e+9;
    String axis "T";
    String ioos_category "Time";
    String long_name "Center time of the day";
    String standard_name "time";
    String time_origin "01-JAN-1970 00:00:00";
    String units "seconds since 1970-01-01T00:00:00Z";
  }
  latitude {
    String _CoordinateAxisType "Lat";
    Float64 actual_range -89.875, 89.875;
    String axis "Y";
    String grid "Uniform grid from -89.875 to 89.875 by 0.25";
    String ioos_category "Location";
    String long_name "Latitude";
    String standard_name "latitude";
    String units "degrees_north";
  }
  longitude {
    String _CoordinateAxisType "Lon";
    Float64 actual_range -179.875, 179.875;
    String axis "X";
    String grid "Uniform grid from -179.875 to 179.875 by 0.25";
    String ioos_category "Location";
    String long_name "Longitude";
    String standard_name "longitude";
    String units "degrees_east";
  }
  ice {
    Float32 _FillValue -9.99;
    Float64 colorBarMaximum 100.0;
    Float64 colorBarMinimum 0.0;
    String ioos_category "Ice Distribution";
    String long_name "Sea ice concentration";
    String units "percent";
    Float32 valid_max 1.0;
    Float32 valid_min 0.0;
  }
  sst {
    Float32 _FillValue -9.99;
    Float64 colorBarMaximum 31.0;
    Float64 colorBarMinimum 20.0;
    String colorBarPalette "Spectrum";
    String ioos_category "Temperature";
    String long_name "Daily sea surface temperature";
    String standard_name "sea_surface_temperature";
    String units "degree_C";
    Float32 valid_max 45.0;
    Float32 valid_min -3.0;
  }
  error {
    Float32 _FillValue -9.99;
    Float64 colorBarMaximum 5.0;
    Float64 colorBarMinimum 0.0;
    String ioos_category "Statistics";
    String long_name "Estimated error standard deviation of analysed_sst";
    String units "degree_C";
    Float32 valid_max 10.0;
    Float32 valid_min 0.0;
  }
  anom {
    Float32 _FillValue -9.99;
    Float64 colorBarMaximum 3.0;
    Float64 colorBarMinimum -3.0;
    String ioos_category "Temperature";
    String long_name "Daily sea surface temperature anomalies";
    String standard_name "surface_temperature_anomaly";
    String units "degree_C";
    Float32 valid_max 12.0;
    Float32 valid_min -12.0;
  }
  NC_GLOBAL {
    String cdm_data_type "Grid";
    String comment "Data was converted from NetCDF-3 to NetCDF-4 format with metadata updates in November 2017.";
    String Conventions "CF-1.10, ACDD-1.3, COARDS";
    String creator_email "oisst-help@noaa.gov";
    String creator_name "NOAA/National Centers for Environmental Information";
    String creator_type "group";
    String creator_url "https://www.ncei.noaa.gov/";
    String date_created "2024-12-12T14:44:00Z";
    String date_modified "2024-12-12T14:44:00Z";
    Float64 Easternmost_Easting 179.875;
    Float64 geospatial_lat_max 89.875;
    Float64 geospatial_lat_min -89.875;
    Float64 geospatial_lat_resolution 0.25;
    String geospatial_lat_units "degrees_north";
    Float64 geospatial_lon_max 179.875;
    Float64 geospatial_lon_min -179.875;
    Float64 geospatial_lon_resolution 0.25;
    String geospatial_lon_units "degrees_east";
    String history "Final file created using preliminary as first guess, and 3 days of AVHRR data. Preliminary uses only 1 day of AVHRR data.
2026-09-23T15:40:30Z (local files)
2026-09-23T15:40:30Z https://erddap.aoml.noaa.gov/hdb/erddap/griddap/SST_OI_DAILY_1981_PRESENT_T.das";
    String id "oisst-avhrr-v02r01.20241127.nc";
    String infoUrl "https://doi.org/10.25921/RE9P-PT57";
    String institution "NOAA/National Centers for Environmental Information";
    String instrument "Earth Remote Sensing Instruments > Passive Remote Sensing > Spectrometers/Radiometers > Imaging Spectrometers/Radiometers > AVHRR > Advanced Very High Resolution Radiometer";
    String instrument_vocabulary "Global Change Master Directory (GCMD) Instrument Keywords";
    String keywords "advanced, analysed, analysis, anomalies, anomaly, avhrr, centers, concentration, daily, data, day, degree, deviation, distribution, earth, Earth Science > Land Surface > Land Temperature > Land Surface Temperature, Earth Science > Oceans > Ocean Temperature > Sea Surface Temperature, environmental, error, estimated, final, high, ice, ice distribution, information, interpolation, land, latitude, longitude, national, ncei, near, nesdis, noaa, nrt, ocean, oceans, oisst, optimum, radiometer, real, resolution, science, sea, sea_surface_temperature, sst, standard, statistics, surface, surface_temperature_anomaly, temperature, time, version, very, vhrr";
    String keywords_vocabulary "GCMD Science Keywords";
    String license "The data may be used and redistributed for free but is not intended
for legal use, since it may contain inaccuracies. Neither the data
Contributor, ERD, NOAA, nor the United States Government, nor any
of their employees or contractors, makes any warranty, express or
implied, including warranties of merchantability and fitness for a
particular purpose, or assumes any legal liability for the accuracy,
completeness, or usefulness, of this information.";
    String metadata_link "https://doi.org/10.25921/RE9P-PT57";
    String naming_authority "gov.noaa.ncei";
    Float64 Northernmost_Northing 89.875;
    String platform "Ships, buoys, Argo floats, MetOp-A, MetOp-B";
    String platform_vocabulary "Global Change Master Directory (GCMD) Platform Keywords";
    String processing_level "NOAA Level 4";
    String product_version "Version v02r01";
    String references "Reynolds, et al.(2007) Daily High-Resolution-Blended Analyses for Sea Surface Temperature (available at https://doi.org/10.1175/2007JCLI1824.1). Banzon, et al.(2016) A long-term record of blended satellite and in situ sea-surface temperature for climate monitoring, modeling and environmental studies (available at https://doi.org/10.5194/essd-8-165-2016). Huang et al. (2020) Improvements of the Daily Optimum Interpolation Sea Surface Temperature (DOISST) Version v02r01, submitted.Climatology is based on 1971-2000 OI.v2 SST. Satellite data: Pathfinder AVHRR SST, Navy AVHRR SST, and NOAA ACSPO SST. Ice data: NCEP Ice and GSFC Ice.";
    String sensor "Thermometer, AVHRR";
    String source "ICOADS, NCEP_GTS, GSFC_ICE, NCEP_ICE, Pathfinder_AVHRR, Navy_AVHRR, NOAA_ACSP";
    String sourceUrl "(local files)";
    Float64 Southernmost_Northing -89.875;
    String standard_name_vocabulary "CF Standard Name Table v70";
    String summary "NOAA/National Centers for Environmental Information (NCEI) 1/4 Degree Daily Optimum Interpolation Sea Surface Temperature (OISST) Analysis, Version 2.1 - Final. NOAAs 1/4-degree Daily Optimum Interpolation Sea Surface Temperature (OISST) (sometimes referred to as Reynolds SST, which however also refers to earlier products at different resolution), currently available as version v02r01, is created by interpolating and extrapolating SST observations from different sources, resulting in a smoothed complete field. The sources of data are satellite (Advanced Very High Resolution Radiometer (AVHRR)) and in situ platforms (i.e., ships and buoys), and the specific datasets employed may change over time. At the marginal ice zone, sea ice concentrations are used to generate proxy SSTs.  A preliminary version of this file is produced in near-real time (1-day latency), and then replaced with a final version after 2 weeks. Note that this is the AVHRR-ONLY DOISST, available from Oct 1981, but there is a companion DOISST product that includes microwave satellite data, available from June 2002";
    String time_coverage_end "2024-11-27T12:00:00Z";
    String time_coverage_start "1981-09-01T12:00:00Z";
    String title "SST Daily Optimum Interpolation (OI)-V2.1, (Advanced Very High Resolution Radiometer (AVHRR)) 1981-present (Tropics)";
    Float64 Westernmost_Easting -179.875;
  }
}

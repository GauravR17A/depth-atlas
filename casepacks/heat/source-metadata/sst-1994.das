Attributes {
    time {
        String long_name "Time";
        String units "days since 1800-01-01 00:00:00";
        String delta_t "0000-00-01 00:00:00";
        String avg_period "0000-00-01 00:00:00";
        String axis "T";
        Float64 actual_range 70857.0, 71221.0;
        UInt32 _ChunkSizes 1;
    }
    lon {
        String axis "X";
        String long_name "Longitude";
        String standard_name "longitude";
        String units "degrees_east";
        Float32 actual_range 0.125, 359.875;
    }
    sst {
        String long_name "Daily Sea Surface Temperature";
        String units "degC";
        Float32 valid_range -3.0, 45.0;
        Float32 missing_value -9.96921E36;
        Float32 precision 2.0;
        String dataset "NOAA High-resolution Blended Analysis";
        String var_desc "Sea Surface Temperature";
        String level_desc "Surface";
        String statistic "Mean";
        String parent_stat "Individual Observations";
        Float32 actual_range -1.8, 34.94;
        UInt32 _ChunkSizes 1, 720, 1440;
    }
    lat {
        String units "degrees_north";
        Float32 actual_range -89.875, 89.875;
        String axis "Y";
        String standard_name "latitude";
        String long_name "Latitude";
    }
    NC_GLOBAL {
        String Conventions "CF-1.5";
        String title "NOAA High-resolution Blended Analysis: Daily Values using AVHRR only";
        String institution "NOAA/NCDC";
        String source "NOAA/NCDC  ftp://eclipse.ncdc.noaa.gov/pub/OI-daily-v2/";
        String history "Thu Aug 24 13:41:50 2017: ncatted -O -a References,global,d,, sst.day.mean.1994.v2.nc
Version 1.0";
        String dataset_title "NOAA Daily Optimum Interpolation Sea Surface Temperature";
        String _NCProperties "version=2,netcdf=4.6.3,hdf5=1.10.5";
        String References "https://www.psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html";
        String comment "Reynolds, et al.(2007) Daily High-Resolution-Blended Analyses for Sea Surface Temperature (available at https://doi.org/10.1175/2007JCLI1824.1). Banzon, et al.(2016) A long-term record of blended satellite and in situ sea-surface temperature for climate monitoring, modeling and environmental studies (available at https://doi.org/10.5194/essd-8-165-2016). Huang, B., C. Liu, V. Banzon, E. Freeman, G. Graham, B. Hankins, T. Smith, and H.-M. Zhang, 2021: Improvements of the Daily Optimum Interpolation Sea Surface Temperature (DOISST) Version 2.1 (available at https://doi.org/10.1175/JCLI-D-20-0166.1). Anomaly is based on 1971-2000 OI.v2 SST. Satellite data: multi-satellite sensor (AVHRR+VIIRS) data. Ice data: NCEP Ice and GSFC Ice. Data less than 15 days old may be subject to revision.";
    }
    DODS_EXTRA {
        String Unlimited_Dimension "time";
    }
}

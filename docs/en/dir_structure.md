# Project Directory

Details of the project structure are as follows:

```ColdFusion
msprof-analyze
├── config                       # Configuration file directory
├── docs                         # Documentation directory
├── msprof_analyze               # Main code package directory
│   ├── advisor                  # msprof-analyze advisor module
│   │   ├── advisor_backend      # advisor backend implementation
│   │   ├── analyzer             # Performance analyzer module
│   │   ├── common               # Common functional module
│   │   ├── config               # Configuration management module
│   │   ├── dataset              # Dataset processing module
│   │   ├── display              # Display and output module
│   │   ├── interface            # Interface definition module
│   │   ├── result               # Result processing module
│   │   ├── rules                # Rule definition module
│   │   └── utils                # Utility functions module
│   ├── cli                      # Command-line interface module
│   ├── cluster_analyse          # Cluster analysis core module
│   │   ├── analysis             # Analysis algorithm implementation
│   │   ├── cluster_data_preprocess # Cluster data preprocessing
│   │   ├── cluster_kernels_analysis # Cluster kernel analysis
│   │   ├── cluster_utils        # Cluster utility functions
│   │   ├── common_func          # Common functionality
│   │   ├── communication_group  # Communication group management
│   │   ├── prof_bean            # Profile data bean definitions
│   │   ├── recipes              # Analysis capability module
│   │   └── resources            # Resource file directory
│   ├── compare_tools            # Performance comparison tool module
│   │   ├── compare_backend      # Comparison backend implementation
│   │   └── compare_interface    # Comparison interface definition
│   ├── prof_common              # Performance analysis common module
│   └── prof_exports             # Profile data export module
├── requirements                 # Dependency management directory
└── test                         # Test directory
```

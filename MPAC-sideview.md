```mermaid
flowchart TB
  %% ===== Side View: 16 masts with three height positions =====

  subgraph LEGEND["图例 Legend（侧视）"]
    direction LR
    Lp02["0.2 m：奇数抱杆安装"]:::h02
    Lp12["1.2 m：全部安装"]:::h12
    Lp22["2.2 m：偶数抱杆安装"]:::h22
    Lempty["灰色：该高度为空位"]:::empty
  end

  DUT{{"DUT（汽车）\n圆心位置（俯视圆心，对应侧视中轴）"}}:::dut

  %% 编码约定：P01 从 0° 起顺时针递增，与俯视图保持一致
  subgraph SIDE["MPAC 侧视示意（16 根抱杆沿环周展开）"]
    direction TB

    H02["高度 0.2 m"]:::axis
    H12["高度 1.2 m"]:::axis
    H22["高度 2.2 m"]:::axis

    subgraph MROW["抱杆编号从左至右：P01 … P16"]
      direction LR

      subgraph P01["P01"]
        direction TB
        P01_22["空位 2.2 m"]:::empty
        P01_12["探头 1.2 m"]:::h12
        P01_02["探头 0.2 m"]:::h02
      end

      subgraph P02["P02"]
        direction TB
        P02_22["探头 2.2 m"]:::h22
        P02_12["探头 1.2 m"]:::h12
        P02_02["空位 0.2 m"]:::empty
      end

      subgraph P03["P03"]
        direction TB
        P03_22["空位 2.2 m"]:::empty
        P03_12["探头 1.2 m"]:::h12
        P03_02["探头 0.2 m"]:::h02
      end

      subgraph P04["P04"]
        direction TB
        P04_22["探头 2.2 m"]:::h22
        P04_12["探头 1.2 m"]:::h12
        P04_02["空位 0.2 m"]:::empty
      end

      subgraph P05["P05"]
        direction TB
        P05_22["空位 2.2 m"]:::empty
        P05_12["探头 1.2 m"]:::h12
        P05_02["探头 0.2 m"]:::h02
      end

      subgraph P06["P06"]
        direction TB
        P06_22["探头 2.2 m"]:::h22
        P06_12["探头 1.2 m"]:::h12
        P06_02["空位 0.2 m"]:::empty
      end

      subgraph P07["P07"]
        direction TB
        P07_22["空位 2.2 m"]:::empty
        P07_12["探头 1.2 m"]:::h12
        P07_02["探头 0.2 m"]:::h02
      end

      subgraph P08["P08"]
        direction TB
        P08_22["探头 2.2 m"]:::h22
        P08_12["探头 1.2 m"]:::h12
        P08_02["空位 0.2 m"]:::empty
      end

      subgraph P09["P09"]
        direction TB
        P09_22["空位 2.2 m"]:::empty
        P09_12["探头 1.2 m"]:::h12
        P09_02["探头 0.2 m"]:::h02
      end

      subgraph P10["P10"]
        direction TB
        P10_22["探头 2.2 m"]:::h22
        P10_12["探头 1.2 m"]:::h12
        P10_02["空位 0.2 m"]:::empty
      end

      subgraph P11["P11"]
        direction TB
        P11_22["空位 2.2 m"]:::empty
        P11_12["探头 1.2 m"]:::h12
        P11_02["探头 0.2 m"]:::h02
      end

      subgraph P12["P12"]
        direction TB
        P12_22["探头 2.2 m"]:::h22
        P12_12["探头 1.2 m"]:::h12
        P12_02["空位 0.2 m"]:::empty
      end

      subgraph P13["P13"]
        direction TB
        P13_22["空位 2.2 m"]:::empty
        P13_12["探头 1.2 m"]:::h12
        P13_02["探头 0.2 m"]:::h02
      end

      subgraph P14["P14"]
        direction TB
        P14_22["探头 2.2 m"]:::h22
        P14_12["探头 1.2 m"]:::h12
        P14_02["空位 0.2 m"]:::empty
      end

      subgraph P15["P15"]
        direction TB
        P15_22["空位 2.2 m"]:::empty
        P15_12["探头 1.2 m"]:::h12
        P15_02["探头 0.2 m"]:::h02
      end

      subgraph P16["P16"]
        direction TB
        P16_22["探头 2.2 m"]:::h22
        P16_12["探头 1.2 m"]:::h12
        P16_02["空位 0.2 m"]:::empty
      end
    end
  end

  SUM["统计：\n编号：P01–P16（沿环周按顺时针编号）\n0.2 m：8 个（奇数抱杆）\n1.2 m：16 个（全部）\n2.2 m：8 个（偶数抱杆）\n总计：32 个双极化探头"]:::summary

  classDef dut fill:#FDE68A,stroke:#B45309,stroke-width:1.5,color:#78350F;
  classDef axis fill:#FFFFFF,stroke:#9E9E9E,stroke-dasharray: 4 3,color:#4A4A4A;
  classDef h02 fill:#E0F7FA,stroke:#00ACC1,stroke-width:1.2,color:#006064;
  classDef h12 fill:#E8F5E9,stroke:#43A047,stroke-width:1.2,color:#1B5E20;
  classDef h22 fill:#F3E8FF,stroke:#7E57C2,stroke-width:1.2,color:#4527A0;
  classDef empty fill:#F5F5F5,stroke:#BDBDBD,stroke-width:1.0,color:#616161;
  classDef summary fill:#FFFFFF,stroke:#111827,stroke-dasharray: 5 3,color:#111827;
  ```

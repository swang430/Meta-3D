```mermaid
flowchart TB
  %% =======================
  %% MPAC MIMO OTA in Microwave OTA Chamber (Schematic)
  %% 16 masts on a 10 m radius ring
  %% Probes: 0.2 m -> 8 units (odd masts)
  %%         1.2 m -> 16 units (all masts)
  %%         2.2 m -> 8 units (even masts)
  %% DUT at center (car)
  %% =======================

  %% Legend
  subgraph LEGEND["图例 Legend"]
    direction LR
    L02["0.2 m 高度（8 个）"]:::h02 --- L12["1.2 m 高度（16 个）"]:::h12 --- L22["2.2 m 高度（8 个）"]:::h22
    noteL["每个节点均为『双极化探头（Dual-Pol）』\n每根抱杆（M1…M16）位于半径 10 m 的圆环上等角分布"]:::legend
  end

  %% DUT at center
  DUT{{"被测物体（汽车）\nDUT (Car) @ Center"}}:::dut

  %% Ring container
  subgraph RING["MPAC 探头环（半径 10 m，16 根抱杆等角分布）"]
    direction TB

    %% Group masts into 4 quadrants just for layout readability
    subgraph Q1["Q1"]
      direction TB
      M1["M1 抱杆"]:::mast
      M2["M2 抱杆"]:::mast
      M3["M3 抱杆"]:::mast
      M4["M4 抱杆"]:::mast
    end
    subgraph Q2["Q2"]
      direction TB
      M5["M5 抱杆"]:::mast
      M6["M6 抱杆"]:::mast
      M7["M7 抱杆"]:::mast
      M8["M8 抱杆"]:::mast
    end
    subgraph Q3["Q3"]
      direction TB
      M9["M9 抱杆"]:::mast
      M10["M10 抱杆"]:::mast
      M11["M11 抱杆"]:::mast
      M12["M12 抱杆"]:::mast
    end
    subgraph Q4["Q4"]
      direction TB
      M13["M13 抱杆"]:::mast
      M14["M14 抱杆"]:::mast
      M15["M15 抱杆"]:::mast
      M16["M16 抱杆"]:::mast
    end
  end

  %% Connect center to ring (conceptual spokes)
  DUT --- M1 & M2 & M3 & M4 & M5 & M6 & M7 & M8
  DUT --- M9 & M10 & M11 & M12 & M13 & M14 & M15 & M16

  %% For each mast, show the three height positions, with population rule:
  %% - 0.2 m populated on odd masts (M1,3,5,...,15) -> total 8
  %% - 1.2 m populated on all masts -> total 16
  %% - 2.2 m populated on even masts (M2,4,6,...,16) -> total 8

  %% ---------- Q1 ----------
  M1 --> M1_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M1 --> M1_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  %% M1 2.2 m empty (not populated)

  M2 --> M2_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M2 --> M2_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22
  %% M2 0.2 m empty

  M3 --> M3_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M3 --> M3_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  %% M3 2.2 m empty

  M4 --> M4_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M4 --> M4_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22
  %% M4 0.2 m empty

  %% ---------- Q2 ----------
  M5 --> M5_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M5 --> M5_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12

  M6 --> M6_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M6 --> M6_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22

  M7 --> M7_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M7 --> M7_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12

  M8 --> M8_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M8 --> M8_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22

  %% ---------- Q3 ----------
  M9 --> M9_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M9 --> M9_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12

  M10 --> M10_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M10 --> M10_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22

  M11 --> M11_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M11 --> M11_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12

  M12 --> M12_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M12 --> M12_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22

  %% ---------- Q4 ----------
  M13 --> M13_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M13 --> M13_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12

  M14 --> M14_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M14 --> M14_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22

  M15 --> M15_02["Probe @ 0.2 m\n(Dual-Pol)"]:::h02
  M15 --> M15_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12

  M16 --> M16_12["Probe @ 1.2 m\n(Dual-Pol)"]:::h12
  M16 --> M16_22["Probe @ 2.2 m\n(Dual-Pol)"]:::h22

  %% Counts summary
  CNT["合计 Summary:\n0.2 m：8 个（奇数抱杆）\n1.2 m：16 个（全部抱杆）\n2.2 m：8 个（偶数抱杆）\n总计：32 个双极化探头"]:::summary

  %% Styles
  classDef dut fill:#FDE68A,stroke:#B45309,stroke-width:1.5,color:#78350F;
  classDef mast fill:#ECEFF1,stroke:#607D8B,stroke-width:1.2,color:#263238;
  classDef h02 fill:#E0F7FA,stroke:#00ACC1,stroke-width:1.2,color:#006064;   %% 0.2 m
  classDef h12 fill:#E8F5E9,stroke:#43A047,stroke-width:1.2,color:#1B5E20;   %% 1.2 m
  classDef h22 fill:#F3E8FF,stroke:#7E57C2,stroke-width:1.2,color:#4527A0;   %% 2.2 m
  classDef legend fill:#FFFFFF,stroke:#9E9E9E,stroke-dasharray: 4 3,color:#4A4A4A;
  classDef summary fill:#FFFFFF,stroke:#111827,stroke-dasharray: 5 3,color:#111827;
  ```
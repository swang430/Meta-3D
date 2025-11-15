```mermaid
flowchart TB
  %% =======================
  %% Top-Down View: MPAC Ring (R = 10 m) with 16 Masts
  %% Even spacing: 360/16 = 22.5° per mast
  %% Odd masts: include 0.2 m probes; Even masts: include 2.2 m probes
  %% All masts include 1.2 m probes (not shown in top view)
  %% =======================

  %% Legend
  subgraph LEGEND["图例 Legend（俯视）"]
    direction LR
    Lodd["奇数号抱杆：含 0.2 m 探头"]:::odd --- Leven["偶数号抱杆：含 2.2 m 探头"]:::even
    Lall["所有抱杆：含 1.2 m 探头（此视图不单画）"]:::legend
  end

  %% DUT at center
  DUT{{"DUT（汽车）\n圆心"}}:::dut

  %% 编码约定：P01 从 0° 起顺时针递增，俯视与侧视共用
  %% Ring (arranged by quadrants for layout only)
  subgraph RING["MPAC 探头环（半径 10 m，16 根抱杆等角分布，步距 22.5°）"]
    direction TB

    %% Q1: 0°..90°
    subgraph Q1["Q1（0°–90°）"]
      direction LR
      P01["P01 @ 0°"]:::odd
      P02["P02 @ 22.5°"]:::even
      P03["P03 @ 45°"]:::odd
      P04["P04 @ 67.5°"]:::even
    end

    %% Q2: 90°..180°
    subgraph Q2["Q2（90°–180°）"]
      direction LR
      P05["P05 @ 90°"]:::odd
      P06["P06 @ 112.5°"]:::even
      P07["P07 @ 135°"]:::odd
      P08["P08 @ 157.5°"]:::even
    end

    %% Q3: 180°..270°
    subgraph Q3["Q3（180°–270°）"]
      direction LR
      P09["P09 @ 180°"]:::odd
      P10["P10 @ 202.5°"]:::even
      P11["P11 @ 225°"]:::odd
      P12["P12 @ 247.5°"]:::even
    end

    %% Q4: 270°..360°
    subgraph Q4["Q4（270°–360°）"]
      direction LR
      P13["P13 @ 270°"]:::odd
      P14["P14 @ 292.5°"]:::even
      P15["P15 @ 315°"]:::odd
      P16["P16 @ 337.5°"]:::even
    end
  end

  %% Spokes (explicit connections)
  DUT --- P01
  DUT --- P02
  DUT --- P03
  DUT --- P04
  DUT --- P05
  DUT --- P06
  DUT --- P07
  DUT --- P08
  DUT --- P09
  DUT --- P10
  DUT --- P11
  DUT --- P12
  DUT --- P13
  DUT --- P14
  DUT --- P15
  DUT --- P16

  %% Ring connections (visual cue for环状布局)
  P01 --- P02
  P02 --- P03
  P03 --- P04
  P04 --- P05
  P05 --- P06
  P06 --- P07
  P07 --- P08
  P08 --- P09
  P09 --- P10
  P10 --- P11
  P11 --- P12
  P12 --- P13
  P13 --- P14
  P14 --- P15
  P15 --- P16
  P16 --- P01

  %% Summary
  SUM["统计：\n• 抱杆 16 根（编号 P01–P16），半径 10 m 等角分布\n• 0.2 m 探头：8 个（奇数号）\n• 1.2 m 探头：16 个（全部）\n• 2.2 m 探头：8 个（偶数号）\n• 总计探头 32 个，均为双极化"]:::summary

  %% Styles (no inline comments on these lines)
  classDef dut fill:#FDE68A,stroke:#B45309,stroke-width:1.6,color:#78350F;
  classDef odd fill:#E0F7FA,stroke:#00ACC1,stroke-width:1.2,color:#006064;
  classDef even fill:#F3E8FF,stroke:#7E57C2,stroke-width:1.2,color:#4527A0;
  classDef legend fill:#FFFFFF,stroke:#9E9E9E,stroke-dasharray: 4 3,color:#4A4A4A;
  classDef summary fill:#FFFFFF,stroke:#111827,stroke-dasharray: 5 3,color:#111827;
  ```

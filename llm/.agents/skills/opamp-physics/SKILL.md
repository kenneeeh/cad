---
name: opamp-physics
description: Interprets measured TwoStage bottlenecks using device roles and qualified physical approximations.
---

Verified topology: TwoStage.cir instantiates MOS devices directly; p045_TT.sp
defines NMOS/PMOS models, not an extra amplifier subcircuit. MOS pin order is
drain, gate, source, bulk. net5 is first-stage output/mp3 gate; net6 is output.

| Devices | Type and role | Width / length / multiplicity controls |
|---|---|---|
| mn1, mn2 | NMOS input differential pair; gates net2/net1, shared source/body net3, drains net4/net5 | wn1 / ln1 / mn1, shared by BOTH devices |
| mp1, mp2 | PMOS first-stage mirror load; sources/bodies VDD, shared gate net4; mp1 drain=gate net4, mp2 drain net5 | wp1 / lp1 / mp1, shared by BOTH devices |
| mn3 | NMOS diode-connected bias reference; drain=gate net7, source/body VSS; fed by ibias | wn3 / ln3 / mn3 |
| mn4 | NMOS input-tail mirror output; drain net3, gate net7, source/body VSS | wn4 / ln4 / mn4 |
| mp3 | PMOS second-stage common-source amplifier; drain net6, gate net5, source/body VDD | wp3 / lp3 / mp3 |
| mn5 | NMOS second-stage sink/mirror output; drain net6, gate net7, source/body VSS | wn5 / ln5 / mn5 |
| cc | Compensation capacitor from net5 to net8 | cap |
| rc | Series compensation resistor from net8 to net6 | res |

These are the 20 YAML sizing parameters. mn2/mp2 are device instance names, not
independent sizing parameters. m-controls are multiplicities, not widths. ibias
and output load CL are fixed by the testbench, not among these sizing actions.
mn3 shares its gate voltage with BOTH mn4 and mn5: changing the reference can
change both stage biases. It is not the second-stage signal amplifier.
Before proposing a hypothesis, silently check its affected devices against this
map. In particular, lp1/wp1/mp1 change the PMOS mirror LOAD, not input-pair gm;
ln1/wn1/mn1 change the NMOS INPUT PAIR. mn3 is the shared reference, mn5 the
output sink. Do not swap these roles in advice or the final parameter table.
Reducing mn3 or wn3 can increase BOTH mirrored currents; it is not a direct
second-stage current reduction. Measured total supply current is not tail current.

Hypotheses, not measured operating points:
- Under a simple matched, saturated mirror approximation, output current depends
  on output/reference m*W/L ratios. At fixed reference current, widening mn3 can
  lower the common gate voltage and mirrored currents; do not assume more mn3
  means more output drive. Short-channel/output-voltage effects require measurement.
- Gain may benefit from gm and output resistance; longer channels can help ro
  but add area/parasitics. Changing load/driver geometry also changes loading/bias.
- In the Miller-dominated regime, UGBW roughly follows gm_input/(2*pi*Cc), and
  slew follows available charging current/relevant capacitance. Smaller Cc may
  improve speed while reducing PM. The resistor's zero depends on the operating
  point; no universal optimal R or monotonic sizing rule is established here.
- Input area/gm may help noise, with bias/parasitic trade-offs. Use measured
  integrated RMS noise and the measured rising slew; do not assume edge symmetry.

Read current targets/grids/units from get_problem. Never invent DC currents, gm,
saturation, poles or a causal explanation from names alone. Distinguish the
verified connections above from a hypothesis and its observed simulation result.
PHM is not abs(phase); zero UGBW/PHM is a penalized no-crossing fallback, not proof
of stability. Feasibility here covers the current testbench, not PVT robustness.

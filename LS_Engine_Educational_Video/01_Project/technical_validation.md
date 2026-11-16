# Technical validation — engine & fuel-control accuracy

Reviewed before rendering. Every statement in narration/graphics was checked against the rules in the brief.

## Engine model (procedural, original geometry)

| Item | Implementation | Status |
|---|---|---|
| Architecture | 90° V8, OHV pushrod, single cam in block, 2 valves/cyl, coil-near-plug coils on the valve covers | ✔ LS Gen III/IV layout |
| Dimensions | Bore spacing 4.40 in (111.8 mm), bore 99 mm, stroke 92 mm, rod 6.098 in, deck 9.24 in, compression height 1.33 in → piston crown reaches the deck at TDC (computed 0.2347 m vs deck 0.235 m) | ✔ (5.3/5.7-class values) |
| Bank layout | Left (driver) bank = odd cylinders 1-3-5-7, offset forward of the right bank (2-4-6-8) | ✔ |
| Crankshaft | Cross-plane, 4 crank pins at 90°, two rods per pin (1/2, 3/4, 5/6, 7/8); pin phasing derived from bank angle + firing order and asserted in code | ✔ |
| Firing order | 1-8-7-2-6-5-4-3, compression TDC every 90° of crank | ✔ |
| Slider-crank | Exact piston position from crank pin and rod length each frame; rod orientation pin→wrist pin | ✔ |
| Camshaft | Rotates at ½ crank speed; valve events: exhaust ≈125–380°, intake ≈345–595° (cycle degrees, 0 = compression TDC) — generic, not an LS cam card | ✔ (illustrative) |
| Fuel injection | **Port** injection: 8 injectors in the intake runners aimed at the intake valve, sequential, closed-valve timing; spray never enters the combustion chamber | ✔ |
| Intake | Centre plenum, 8 runners, drive-by-wire throttle body at the front, MAF in the inlet duct, MAP on the manifold | ✔ |
| Sensors | ECT on the front of the left cylinder head (Gen III location), TPS on the throttle body, CKP on the block, upstream O₂ (B1S1 / B2S1) in each exhaust downpipe before the catalyst | ✔ |
| ECU | Generic GM-style finned PCM with two harness connectors, no logos | ✔ (generic) |

### Simplifications (stated honestly)
* No water jackets, oil passages, timing chain, catalytic converters or accessory brackets.
* Valves are drawn parallel to the bore axis (real LS valve angle ≈15°); rocker geometry simplified.
* The cam lobes are visual (rotate with the cam) and do not drive the lifters geometrically; valve lift
  comes from the cycle-angle functions above.
* Crank speed is shown in **slow motion** (0.32–0.75 rev/s) so individual strokes are readable at 30 fps;
  the engine *sound* plays at a real idle speed (~680–1 500 rpm).
* The 3D fuel map is a generic illustrative surface (RPM × load), **not** real calibration data.
* STFT/LTFT/O₂ values in the graphics are illustrative signal shapes, not logged data.

## Fuel-control statements

| Rule from the brief | How it is respected |
|---|---|
| LS = port injection, not direct injection | Narration: «ترش الوقود عند مجاري السحب»; injector label “Port Fuel Injector”; spray modelled in the port |
| Open Loop still uses MAF/MAP/RPM/temp/throttle | S4 graphic: “يستخدم: MAF • MAP • RPM • ECT • TPS + خرائط الوقود المبرمجة”; narration «يعتمد على الخرائط والحساسات» |
| Open Loop = O₂ feedback not used for fuel correction | Narration «ما يستخدم حساس الأكسجين لتصحيح الوقود»; graphic “تصحيح الوقود من حساس O₂: غير مُفعّل”; O₂ harness dim, no pulses |
| Closed Loop uses **upstream** O₂ feedback | O₂ sensors placed before the catalyst; label “Upstream O₂ (Bank 1 Sensor 1)” |
| STFT = short-term, LTFT = learned long-term | Dials: STFT fast oscillation, LTFT slow drift “يتغير ببطء ويُحفظ”; pulse width shown as base × (1 + STFT + LTFT) |
| Switching depends on calibration, not coolant temp only | S5 checklist lists temperature, O₂ readiness and run-time/calibration conditions; narration «إذا تحققت شروط البرمجة»; footnote “الشروط الدقيقة تختلف حسب معايرة كل محرك” |
| High load ≠ always Open Loop | Narration says «بعض ظروف الحمل العالي» (some conditions), plus the calibration footnote |
| 14.7:1 not claimed as universal target | No AFR number is claimed anywhere; narration says «حسب نظام التحكم والهدف المطلوب» |
| Commanded vs measured | ECU command pulses (to injectors) and O₂ feedback (to ECU) are separate, differently coloured paths |
| Narrowband vs wideband | Graph explicitly labelled “Narrowband O₂ (V)”, 0.1–0.9 V switching, rich above / lean below ≈0.45 V |
| No invented LS calibration values | No thresholds (temperatures, times, loads) are stated as LS calibration values; the 90 °C on the gauge is an illustrative warm-engine reading |

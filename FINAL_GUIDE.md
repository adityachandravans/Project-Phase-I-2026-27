# Final Project Guide: UART Desktop Application with Arduino Nano + UDB + 16x2 LCD

Files in this folder
| File | Purpose |
|---|---|
| `UDB_Final/UDB_Final.ino` | Arduino Nano firmware |
| `udb_app.py` | Python / tkinter desktop application |
| `FINAL_GUIDE.md` | This guide |

## 1. What the project does (mapped to your task sheet)

| Task | Done by |
|---|---|
| 1 Hardware | Nano + UDB + 16x2 LCD (I2C backpack) |
| 2 Arduino IDE + basic programming | Boot test and reset sketch already done; upload `UDB_Final.ino` |
| 3 UART on Nano, Serial Monitor, strings both ways | Section 6 |
| 4 Same serial communication in Python with UI | `udb_app.py` |
| 5 Display different data parameters | LEDs, bars, numbers, labelled channels |
| 6 Merge and split data strings | `build_command()` / `parse_data()` in Python, `parseFrame()` / `sendFrame()` in Arduino |
| 7 Exchange up to 16 Boolean + 16 Analog values | Every frame carries 16 + 16 in each direction |
| 8 UI displaying the exchanged parameters | Left panel (inputs), right panel (outputs), raw log |
| 9 Industry-specific version | NOT possible yet: waits for CERO Automation inputs (section 9) |
| 10 Documentation | This guide + screenshots as a base; CERO's format is still needed |

## 2. Connections

Power off while wiring. Nano USB cable stays connected to the PC.

### 2.1 Nano
Press the Nano firmly into **Slot 3 (ARDUINO NANO)**, USB port towards the bottom edge (terminal-block side).

### 2.2 LCD (I2C backpack) to the UDB I2C / DS1307 header
The right side of the UDB has a 4-pin header labelled **"I2C DS1307"**. From the manual photo its pins read D15, D14, 5V, GND (top to bottom). D15 = SCL and D14 = SDA, the same order as the Arduino header next to AREF.

| LCD backpack | UDB I2C header pin | Wire |
|---|---|---|
| GND | GND | black |
| VCC | 5V | red |
| SDA | D14 (SDA) | blue |
| SCL | D15 (SCL) | yellow |

Before trusting this, do a **continuity test** with a multimeter (beep mode): one probe on the Nano's own A4 pin and the other on the header pin marked D14. It must beep. Repeat for A5 and D15. If either does not beep, take the LCD wires from the pins labelled A4 and A5 beside the Nano slot instead.

Your wire guide shows "A4 = D14". On the Nano, A4 is actually pin 18 and A5 is pin 19; D14/D15 is just the UDB's silkscreen name. The connection is the same.

You need 4 female-to-female jumper wires (or a breadboard with male wires). No DS1307 module is needed.

### 2.3 Jumper caps (small plastic caps that slide over 2 pins)
Read from the UDB silkscreen. Check each row label on your board.

| Header | Row | Cap | Needed for |
|---|---|---|---|
| JP7 SET | POT - A3 | yes | pot value on analog A00 |
| JP7 SET | RY1 - A0, RY2 - A1, RY3 - A2 | yes | relays 1, 2, 3 |
| JP8 SET | D11 - SW1, D10 - SW2, D9 - SW3, D6 - SW4 | yes | 4 push buttons |
| JP8 SET | BUZ - D3 | yes | buzzer |
| JP8 SET | D12 - RF_RX, D13 - RF_TX | NO | RF modules, unused |
| JP5 (UART / SIM800L) | any cap | REMOVE | it can block uploads |

Minimum for a good demo: POT - A3, SW1 and SW2. Add the rest to use all outputs.
Power the relays properly: use the DC jack or USB-C and set the +5VE switch ON.

### 2.4 Optional external LEDs
Only if you have a breadboard: D5 (PWM, analog A00) and D4 (boolean B05), each through a 220 ohm resistor to the LED's long leg, short leg to GND. The on-board green LED on D13 needs no wiring.

### 2.5 Summary

| Function | Nano pin |
|---|---|
| Relay 1, 2, 3 | A0, A1, A2 |
| LED D13 / Buzzer / LED D4 | D13 / D3 / D4 |
| SW1, SW2, SW3, SW4 | D11, D10, D9, D6 |
| Pot | A3 |
| LCD SDA / SCL | A4 / A5 |
| PWM output | D5 |
| UART to PC | D0 / D1 (USB), keep free |

## 3. Channel map (16 Boolean + 16 Analog)

| Direction | Real channels | Remaining |
|---|---|---|
| Boolean, Arduino to PC | B00 SW1, B01 SW2, B02 SW3, B03 SW4 | B04-B15 echo what the PC sent |
| Boolean, PC to Arduino | B00-B02 Relays 1-3, B03 LED D13, B04 Buzzer, B05 LED D4 | B06-B15 virtual, stored and echoed |
| Analog, Arduino to PC | A00 pot (A3), A01 A6, A02 A7, A03 pot %, A04 uptime s | A05-A15 echo what the PC sent |
| Analog, PC to Arduino | A00 PWM on D5 | A01-A15 virtual, stored and echoed |

The Nano has only 8 analog pins, and A4/A5 are used by the LCD. So only a few channels are physical and the rest are virtual registers that prove all 16 + 16 values travel both ways. Explain it this way in the viva.

## 4. Protocol (ASCII, one line per frame)

```
Arduino -> PC :  D,<16 bits>,<a0>,<a1>,...,<a15>
PC -> Arduino :  C,<16 bits>,<v0>,<v1>,...,<v15>
Example       :  D,1000000000000000,512,300,0,...
```
- Merge: build the string (`build_command`, `sendFrame`).
- Split: `split(",")` in Python, `strtol` in Arduino. Frames with wrong length or bad characters are ignored.
- Frames are sent every 300 ms.
- At boot the Arduino prints `I,LCD=0x27` (or `NOT_FOUND`). The app shows it as an info line in the log.

## 5. LCD display
Pages change every 2.5 s:
- Page 1: row 1 = the 16 boolean inputs, row 2 = the 16 boolean outputs ("No PC link..." if the app is not connected).
- Pages 2-5: the 16 analog values, 4 per page, as `index:value`.

## 6. Running it step by step

### 6.1 Arduino
1. Install the library **LiquidCrystal I2C** (Frank de Brabander) in Tools > Manage Libraries.
2. Tools: Board **Arduino Nano**, Processor **ATmega328P (Old Bootloader)**, correct Port (the settings that worked for your boot test).
3. Open `UDB_Final/UDB_Final.ino` and Upload.
4. Open the Serial Monitor (9600 baud, Newline). You see `I,LCD=0x27` and then lines like `D,0000000000000000,512,...` every 300 ms.
5. Task 3 test: send `C,1000000000000000,800,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0`. Relay 1 clicks and the LCD changes.
6. **Close the Serial Monitor** before the next step.

### 6.2 Python
1. Install Python 3.9+ (tick "Add to PATH"; tkinter is included).
2. `pip install pyserial`
3. `python udb_app.py`
4. Choose the COM port, baud 9600, press **Connect**, wait 2 s. The status turns green.
5. No hardware? Choose **SIMULATOR**.

## 7. Demo script (5 minutes)
1. Show the wiring. The LCD shows the pages.
2. Connect the app: the status is green and the LCD says RX frames are arriving (no "No PC link").
3. Press SW1 on the board: LED B00 lights in the app and the first bit changes on the LCD.
4. Turn the blue pot: bar A00 moves and A03 shows the percentage.
5. Tick Relay 1 in the app: the relay clicks. Tick LED D13 and Buzzer.
6. Tick B10 and move slider A09: they appear in the left panel (echo), proving 16 + 16 both ways.
7. Show the raw log and explain merge and split.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| Upload fails (not in sync) | Processor Old Bootloader; data cable; remove JP5 cap; close Serial Monitor |
| LCD blank | Turn the blue pot on the backpack; check the 4 wires and the continuity test; the log shows `LCD=NOT_FOUND` if the LCD is not on the I2C bus |
| LCD garbage | Library not installed, or SDA/SCL swapped |
| No data in the app | Wrong port, Serial Monitor still open, or wait 2 s after Connect |
| Relay reversed | `OUT_ACTIVE_HIGH = false` in the sketch |
| Buttons reversed | `BTN_ACTIVE_LOW = false` |
| Relay or buzzer dead | Missing JP7/JP8 cap on that row, or no 5V on the DC jack |

## 9. Still open
- **Task 9** needs CERO Automation's inputs (variable names, units, limits, alarms). Until then say: "The generic 16 + 16 framework is complete. Industry customisation (labels, scaling, alarms) follows once CERO gives the inputs." Changing it later means editing the label lists at the top of `udb_app.py` and the scaling in the firmware.
- **Task 10** needs CERO's documentation format. Use this guide plus screenshots of the app, the LCD and the wiring as the content.

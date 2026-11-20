#include <LiquidCrystal_I2C.h>

/*
  UDB_Final.ino
  Arduino Nano in Slot 3 of the Amotech Universal Development Board (UDB)
  + 16x2 LCD with I2C backpack.

  Exchanges 16 Boolean + 16 Analog values with the Python desktop app (UART, 9600).

  PROTOCOL  (ASCII, one line per frame, '\n' terminated)
    Arduino -> PC :  D,<16 bits>,<a0>,...,<a15>
    PC -> Arduino :  C,<16 bits>,<v0>,...,<v15>
    bits = 16 characters '0'/'1' (bit 0 first); analog values 0..1023

  BOOLEAN  Arduino -> PC (inputs)
    B00 SW1 (D11)   B01 SW2 (D10)   B02 SW3 (D9)   B03 SW4 (D6)
    B04..B15 : echo of what the PC sent (virtual registers)
  BOOLEAN  PC -> Arduino (outputs)
    B00 Relay1 (A0)  B01 Relay2 (A1)  B02 Relay3 (A2)
    B03 LED D13 (on-board green)  B04 Buzzer (D3)  B05 LED D4 (optional external)
    B06..B15 : virtual (stored and echoed back)
  ANALOG   Arduino -> PC
    A00 POT on A3 (0..1023)   A01 A6 input   A02 A7 input
    A03 POT in percent (0..100)   A04 uptime in seconds (wraps at 1024)
    A05..A15 : echo of what the PC sent
  ANALOG   PC -> Arduino
    A00 : PWM on D5 (0..1023 -> 0..255), e.g. optional LED on D5
    A01..A15 : virtual (stored and echoed back)

  LCD pages (change every 2.5 s):
    page 0 : row 1 = 16 boolean inputs, row 2 = 16 boolean outputs
    page 1-4 : the 16 analog inputs, 4 per page ("idx:value")

  Library: "LiquidCrystal I2C" by Frank de Brabander (Library Manager).
  Board: Arduino Nano, Processor: ATmega328P (Old Bootloader), 9600 baud.
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ---------------- pin configuration (UDB silkscreen, see guide) ----------------
const uint8_t BTN_PINS[4] = {11, 10, 9, 6};            // SW1..SW4 (JP8 caps)
const bool    BTN_ACTIVE_LOW = true;                   // false if buttons read inverted
const uint8_t OUT_PINS[6] = {A0, A1, A2, 13, 3, 4};    // Relay1-3 (JP7), LED D13, buzzer D3 (JP8), LED D4
const bool    OUT_ACTIVE_HIGH = true;                  // false if a relay/buzzer is inverted
const uint8_t PWM_PIN = 5;
const uint8_t ADC_POT = A3;                            // on-board pot (JP7 cap POT-A3)
const uint8_t ADC_X1 = A6, ADC_X2 = A7;                // spare analog-only pins

const unsigned long BAUD = 9600;
const unsigned long TX_PERIOD_MS = 300;
const unsigned long LCD_PERIOD_MS = 400;
const unsigned long PAGE_MS = 2500;
// ------------------------------------------------------------------------------

LiquidCrystal_I2C *lcd = nullptr;
bool lcdOk = false;

bool bOut[16], bIn[16];
int  aOut[16], aIn[16];

char rxBuf[200];
uint8_t rxLen = 0;
unsigned long lastTx = 0, lastLcd = 0, lastRx = 0, lastPage = 0;
uint8_t page = 0;

uint8_t findLcd() {
  const uint8_t cand[4] = {0x27, 0x3F, 0x20, 0x38};
  for (uint8_t i = 0; i < 4; i++) {
    Wire.beginTransmission(cand[i]);
    if (Wire.endTransmission() == 0) return cand[i];
  }
  return 0;
}

void applyOutputs() {
  for (uint8_t i = 0; i < 6; i++) {
    bool level = OUT_ACTIVE_HIGH ? bOut[i] : !bOut[i];
    digitalWrite(OUT_PINS[i], level ? HIGH : LOW);
  }
  analogWrite(PWM_PIN, constrain(aOut[0], 0, 1023) / 4);
}

bool parseFrame(char *line) {
  if (line[0] != 'C' || line[1] != ',') return false;
  char *p = line + 2;
  bool tmpB[16];
  for (uint8_t i = 0; i < 16; i++) {
    if (p[i] != '0' && p[i] != '1') return false;
    tmpB[i] = (p[i] == '1');
  }
  p += 16;
  int tmpA[16];
  for (uint8_t i = 0; i < 16; i++) {
    if (*p != ',') return false;
    p++;
    char *end;
    long v = strtol(p, &end, 10);
    if (end == p) return false;
    tmpA[i] = constrain((int)v, 0, 1023);
    p = end;
  }
  for (uint8_t i = 0; i < 16; i++) { bOut[i] = tmpB[i]; aOut[i] = tmpA[i]; }
  return true;
}

void readSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuf[rxLen] = '\0';
      if (rxLen > 0 && parseFrame(rxBuf)) {
        lastRx = millis();
        applyOutputs();
      }
      rxLen = 0;
    } else if (rxLen < sizeof(rxBuf) - 1) {
      rxBuf[rxLen++] = c;
    } else {
      rxLen = 0;
    }
  }
}

void sampleInputs() {
  int pot = analogRead(ADC_POT);
  for (uint8_t i = 0; i < 16; i++) {
    bIn[i] = (i < 4) ? ((digitalRead(BTN_PINS[i]) == LOW) == BTN_ACTIVE_LOW) : bOut[i];
  }
  aIn[0] = pot;
  aIn[1] = analogRead(ADC_X1);
  aIn[2] = analogRead(ADC_X2);
  aIn[3] = (int)((long)pot * 100L / 1023L);
  aIn[4] = (int)((millis() / 1000UL) % 1024UL);
  for (uint8_t i = 5; i < 16; i++) aIn[i] = aOut[i];
}

void sendFrame() {
  Serial.print(F("D,"));
  for (uint8_t i = 0; i < 16; i++) Serial.print(bIn[i] ? '1' : '0');
  for (uint8_t i = 0; i < 16; i++) { Serial.print(','); Serial.print(aIn[i]); }
  Serial.print('\n');
}

void updateLcd() {
  if (!lcdOk) return;
  char line[17];
  if (page == 0) {
    for (uint8_t i = 0; i < 16; i++) line[i] = bIn[i] ? '1' : '0';
    line[16] = '\0';
    lcd->setCursor(0, 0); lcd->print(line);
    if (millis() - lastRx > 3000) {
      lcd->setCursor(0, 1); lcd->print(F("No PC link...   "));
    } else {
      for (uint8_t i = 0; i < 16; i++) line[i] = bOut[i] ? '1' : '0';
      lcd->setCursor(0, 1); lcd->print(line);
    }
  } else {
    uint8_t b = (page - 1) * 4;
    snprintf(line, sizeof(line), "%2d:%4d %2d:%4d ", b, aIn[b], b + 1, aIn[b + 1]);
    lcd->setCursor(0, 0); lcd->print(line);
    snprintf(line, sizeof(line), "%2d:%4d %2d:%4d ", b + 2, aIn[b + 2], b + 3, aIn[b + 3]);
    lcd->setCursor(0, 1); lcd->print(line);
  }
}

void setup() {
  Serial.begin(BAUD);
  for (uint8_t i = 0; i < 4; i++) pinMode(BTN_PINS[i], INPUT_PULLUP);
  for (uint8_t i = 0; i < 6; i++) pinMode(OUT_PINS[i], OUTPUT);
  pinMode(PWM_PIN, OUTPUT);
  for (uint8_t i = 0; i < 16; i++) { bOut[i] = false; aOut[i] = 0; bIn[i] = false; aIn[i] = 0; }
  applyOutputs();

  Wire.begin();
  uint8_t addr = findLcd();
  if (addr) {
    lcd = new LiquidCrystal_I2C(addr, 16, 2);
    lcd->init();
    lcd->backlight();
    lcdOk = true;
    lcd->setCursor(0, 0); lcd->print(F("UDB + Nano UART"));
    lcd->setCursor(0, 1); lcd->print(F("16 Bool/16 Analg"));
    delay(1500);
    lcd->clear();
  }
  Serial.print(F("I,LCD="));
  if (addr) { Serial.print(F("0x")); Serial.println(addr, HEX); }
  else Serial.println(F("NOT_FOUND"));
}

void loop() {
  readSerial();
  unsigned long now = millis();
  if (now - lastTx >= TX_PERIOD_MS) {
    lastTx = now;
    sampleInputs();
    sendFrame();
  }
  if (now - lastPage >= PAGE_MS) {
    lastPage = now;
    page = (page + 1) % 5;
  }
  if (now - lastLcd >= LCD_PERIOD_MS) {
    lastLcd = now;
    updateLcd();
  }
}

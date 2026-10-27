/*
 * SonicMortise - Trusted Sensor-Data Attestation using Ultrasonic Connectors
 * Target Board: ESP32-WROOM-32 DevKit V1
 *
 * Connectors & Pinout:
 * - 40 kHz Transmitter (+): GPIO 18 (via 100 ohm)
 * - 40 kHz Transmitter (-): GPIO 19 (via 100 ohm)
 * - 40 kHz Receiver Amplified (from MCP6002 Op-Amp Pin 7): GPIO 34 (via 1k ohm)
 * - Onboard LED: GPIO 2
 */

#include <Arduino.h>
#include <mbedtls/md.h>

const int PIN_TX_POS = 18;
const int PIN_TX_NEG = 19;
const int PIN_RX_ADC = 34;
const int PIN_SENSOR_ANALOG = 32;
const int PIN_STATUS_LED = 2;

const int SAMPLES_COUNT = 300;
uint16_t adc_buffer[SAMPLES_COUNT];
const char* HMAC_SECRET_KEY = "SonicMortiseSecretKeyVITPune";
uint32_t sequence_id = 1;

struct EnrolledProfile {
  bool is_enrolled;
  uint8_t challenge_code;
  float baseline_dc;
  float peak_amplitude;
  float time_gated_energy;
  int onset_sample_idx;
  float waveform_template[SAMPLES_COUNT];
};

EnrolledProfile golden_profile = {false, 0, 2048.0, 0.0, 0.0, 0};

void transmit_ultrasonic_burst(int num_cycles) {
  for (int i = 0; i < num_cycles; i++) {
    digitalWrite(PIN_TX_POS, HIGH);
    digitalWrite(PIN_TX_NEG, LOW);
    delayMicroseconds(12);

    digitalWrite(PIN_TX_POS, LOW);
    digitalWrite(PIN_TX_NEG, HIGH);
    delayMicroseconds(12);
  }
  digitalWrite(PIN_TX_POS, LOW);
  digitalWrite(PIN_TX_NEG, LOW);
}

void capture_acoustic_response() {
  noInterrupts();
  for (int i = 0; i < SAMPLES_COUNT; i++) {
    adc_buffer[i] = analogRead(PIN_RX_ADC);
  }
  interrupts();
}

String generate_hmac_sha256(String message, const char* key) {
  byte hmacResult[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)key, strlen(key));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)message.c_str(), message.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);

  String hashStr = "";
  for (int i = 0; i < 32; i++) {
    char buf[3];
    sprintf(buf, "%02x", hmacResult[i]);
    hashStr += buf;
  }
  return hashStr;
}

void run_interrogation(uint8_t challenge_code, bool do_enrollment) {
  int burst_cycles = 10 + (challenge_code % 4) * 4;
  transmit_ultrasonic_burst(burst_cycles);
  capture_acoustic_response();

  float pre_sum = 0;
  for (int i = 0; i < 30; i++) pre_sum += adc_buffer[i];
  float dc_baseline = pre_sum / 30.0;

  float max_dev = 0;
  float gated_energy = 0;
  int onset_idx = -1;
  int clip_count = 0;

  for (int i = 0; i < SAMPLES_COUNT; i++) {
    float dev = abs(adc_buffer[i] - dc_baseline);
    if (dev > max_dev) max_dev = dev;
    if (onset_idx == -1 && i > 15 && dev > 50.0) onset_idx = i;
    gated_energy += (dev * dev);
    if (adc_buffer[i] <= 15 || adc_buffer[i] >= 4080) clip_count++;
  }

  bool quality_pass = true;
  String reason = "OK";
  if (dc_baseline < 800 || dc_baseline > 3300) {
    quality_pass = false; reason = "BASELINE_BIAS_FAULT";
  } else if (clip_count > 120) {
    quality_pass = false; reason = "EXCESSIVE_CLIPPING";
  } else if (max_dev < 30.0) {
    quality_pass = false; reason = "WEAK_SIGNAL_TIMEOUT";
  }

  String attestation_state = "INVALID_INDETERMINATE";
  float similarity_score = 0.0;

  if (do_enrollment) {
    if (quality_pass) {
      golden_profile.is_enrolled = true;
      golden_profile.baseline_dc = dc_baseline;
      golden_profile.peak_amplitude = max_dev;
      golden_profile.time_gated_energy = gated_energy;
      golden_profile.onset_sample_idx = onset_idx;
      for (int i = 0; i < SAMPLES_COUNT; i++) golden_profile.waveform_template[i] = adc_buffer[i];
      attestation_state = "ENROLLED";
      similarity_score = 100.0;
    }
  } else {
    if (!quality_pass) {
      attestation_state = "INVALID_INDETERMINATE";
    } else if (!golden_profile.is_enrolled) {
      attestation_state = "INVALID_INDETERMINATE";
      reason = "NO_ENROLLED_BASELINE";
    } else {
      float sum_ab = 0, sum_aa = 0, sum_bb = 0;
      for (int i = 0; i < SAMPLES_COUNT; i++) {
        float a = adc_buffer[i] - dc_baseline;
        float b = golden_profile.waveform_template[i] - golden_profile.baseline_dc;
        sum_ab += a * b; sum_aa += a * a; sum_bb += b * b;
      }
      float denom = sqrt(sum_aa * sum_bb);
      float norm_corr = (denom > 0.0001) ? (sum_ab / denom) : 0.0;
      similarity_score = constrain(norm_corr * 100.0, 0.0, 100.0);

      if (similarity_score >= 75.0) attestation_state = "MATCH";
      else if (similarity_score >= 50.0) { attestation_state = "INVALID_INDETERMINATE"; reason = "UNCERTAINTY_REGION"; }
      else { attestation_state = "MISMATCH"; reason = "ACOUSTIC_MISMATCH"; }
    }
  }

  digitalWrite(PIN_STATUS_LED, (attestation_state == "MATCH") ? HIGH : LOW);

  int raw_sensor = analogRead(PIN_SENSOR_ANALOG);
  float sim_temp = 25.0 + (raw_sensor / 4095.0) * 15.0;
  float sim_pressure = 101.32;

  String payload = String(sequence_id) + ":" + String(challenge_code) + ":" + attestation_state + ":" + String(sim_temp, 2);
  String hmac_sig = generate_hmac_sha256(payload, HMAC_SECRET_KEY);

  Serial.print("{\"type\":\"ATTESTATION\",");
  Serial.print("\"seq\":"); Serial.print(sequence_id++); Serial.print(",");
  Serial.print("\"challenge\":"); Serial.print(challenge_code); Serial.print(",");
  Serial.print("\"state\":\""); Serial.print(attestation_state); Serial.print("\",");
  Serial.print("\"reason\":\""); Serial.print(reason); Serial.print("\",");
  Serial.print("\"score\":"); Serial.print(similarity_score, 1); Serial.print(",");
  Serial.print("\"dc_offset\":"); Serial.print(dc_baseline, 1); Serial.print(",");
  Serial.print("\"peak_amp\":"); Serial.print(max_dev, 1); Serial.print(",");
  Serial.print("\"energy\":"); Serial.print(gated_energy, 0); Serial.print(",");
  Serial.print("\"onset_idx\":"); Serial.print(onset_idx); Serial.print(",");
  Serial.print("\"sensor\":{\"temp\":"); Serial.print(sim_temp, 2); Serial.print(",\"pressure\":"); Serial.print(sim_pressure, 2); Serial.print("},");
  Serial.print("\"hmac\":\""); Serial.print(hmac_sig); Serial.print("\",");
  Serial.print("\"wave\":[");
  for (int i = 0; i < SAMPLES_COUNT; i += 3) {
    Serial.print(adc_buffer[i]);
    if (i + 3 < SAMPLES_COUNT) Serial.print(",");
  }
  Serial.println("]}");
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TX_POS, OUTPUT);
  pinMode(PIN_TX_NEG, OUTPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n'); cmd.trim();
    if (cmd.startsWith("VERIFY")) run_interrogation(5, false);
    else if (cmd.startsWith("ENROLL")) run_interrogation(5, true);
  }
  static unsigned long last = 0;
  if (millis() - last > 1500) {
    last = millis();
    run_interrogation(5, false);
  }
}

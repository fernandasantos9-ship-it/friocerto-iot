#!/usr/bin/env python3
"""Simulador dos 14 sensores de temperatura e umidade da FrioCerto.

Publica uma leitura por loja a cada INTERVAL_S segundos no tópico
    friocerto/{regiao}/{loja}/{camara}/telemetria
e, depois de ANOMALY_START_S segundos, faz uma das lojas sair da faixa 2-8 °C
(por padrão a loja_07 sobe para ~12 °C durante 15 minutos) para demonstrar o alerta.

Configuração por variáveis de ambiente (todas opcionais):
    BROKER_HOST (localhost)   BROKER_PORT (1883)   INTERVAL_S (2; em produção seria 60)
    ANOMALY_LOJA (loja_07)    ANOMALY_START_S (60) ANOMALY_DURATION_S (900)
    ANOMALY_TEMP_C (12.0)
"""
import json
import os
import random
import time

import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
INTERVAL_S = float(os.getenv("INTERVAL_S", "2"))
ANOMALY_LOJA = os.getenv("ANOMALY_LOJA", "loja_07")
ANOMALY_START_S = float(os.getenv("ANOMALY_START_S", "60"))
ANOMALY_DURATION_S = float(os.getenv("ANOMALY_DURATION_S", "900"))
ANOMALY_TEMP_C = float(os.getenv("ANOMALY_TEMP_C", "12.0"))

CAMARA = "cf01"
QOS_TELEMETRIA = 1  # pelo menos uma vez (decisão A.3.b)

# 14 lojas do ABC distribuídas por região (4 + 4 + 3 + 3)
REGIOES = {
    "santo_andre": ["loja_01", "loja_02", "loja_03", "loja_04"],
    "sao_bernardo": ["loja_05", "loja_06", "loja_07", "loja_08"],
    "sao_caetano": ["loja_09", "loja_10", "loja_11"],
    "diadema": ["loja_12", "loja_13", "loja_14"],
}
LOJAS = [(regiao, loja) for regiao, lojas in REGIOES.items() for loja in lojas]


def topico(regiao, loja, tipo):
    return f"friocerto/{regiao}/{loja}/{CAMARA}/{tipo}"


def novo_cliente():
    """Cria o cliente MQTT, compatível com paho-mqtt 1.x e 2.x."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="friocerto-publisher")
    except AttributeError:  # paho-mqtt 1.x
        return mqtt.Client(client_id="friocerto-publisher")


def proxima_temperatura(estado, loja):
    """Passeio aleatório limitado a 3-7 °C (dentro da faixa 2-8 °C)."""
    t = estado[loja] + random.uniform(-0.25, 0.25)
    estado[loja] = min(max(t, 3.0), 7.0)
    return round(estado[loja], 2)


def em_anomalia(decorrido_s):
    return ANOMALY_START_S <= decorrido_s < ANOMALY_START_S + ANOMALY_DURATION_S


def rodar(client):
    estado = {loja: random.uniform(4.0, 6.0) for _, loja in LOJAS}
    inicio = time.time()
    anomalia_ativa = False
    while True:
        agora = time.time()
        anomalia = em_anomalia(agora - inicio)
        if anomalia != anomalia_ativa:
            anomalia_ativa = anomalia
            print(f"[{time.strftime('%H:%M:%S')}] anomalia {'INICIADA' if anomalia else 'ENCERRADA'} em {ANOMALY_LOJA}")
        for regiao, loja in LOJAS:
            temp = proxima_temperatura(estado, loja)
            if loja == ANOMALY_LOJA and anomalia:
                temp = round(ANOMALY_TEMP_C + random.uniform(-0.3, 0.3), 2)
            payload = {
                "sensor_id": "s" + loja.split("_")[1],
                "temp_c": temp,
                "umid_pct": round(random.uniform(45, 65), 1),
                "ts": int(agora),
            }
            client.publish(topico(regiao, loja, "telemetria"), json.dumps(payload), qos=QOS_TELEMETRIA)
        time.sleep(INTERVAL_S)


def main():
    client = novo_cliente()
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    for regiao, loja in LOJAS:  # status retido: quem assinar depois já sabe que o sensor está online
        client.publish(topico(regiao, loja, "status"), "online", qos=1, retain=True)
    print(f"Publicando {len(LOJAS)} sensores em {BROKER_HOST}:{BROKER_PORT} a cada {INTERVAL_S:g} s "
          f"(anomalia em {ANOMALY_LOJA} após {ANOMALY_START_S:g} s). Ctrl+C para parar.")
    try:
        rodar(client)
    except KeyboardInterrupt:
        pass
    finally:
        for regiao, loja in LOJAS:
            client.publish(topico(regiao, loja, "status"), "offline", qos=1, retain=True)
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
        print("Publisher encerrado.")


if __name__ == "__main__":
    main()

"""Conexão MQTT (paho) com reconexão automática."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

import paho.mqtt.client as mqtt

log = logging.getLogger("sfal.mqtt")


def broker_address() -> tuple[str, int]:
    return os.environ.get("SFAL_MQTT_HOST", "localhost"), int(os.environ.get("SFAL_MQTT_PORT", "1883"))


def make_client(
    client_id: str,
    on_connect: Callable[[mqtt.Client], None] | None = None,
    on_message: Callable[[str, str], None] | None = None,
    will: tuple[str, str] | None = None,
) -> mqtt.Client:
    """Cria o cliente e inicia a thread de rede. Conecta em segundo plano e reconecta sozinho."""
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)
    user = os.environ.get("SFAL_MQTT_USER")
    if user:
        c.username_pw_set(user, os.environ.get("SFAL_MQTT_PASS", ""))
    if will:
        c.will_set(will[0], will[1], qos=1, retain=True)
    c.reconnect_delay_set(min_delay=1, max_delay=10)

    def _on_connect(client, _userdata, _flags, reason_code, _props):
        if reason_code.is_failure:
            log.error("%s: broker recusou a conexão: %s", client_id, reason_code)
            return
        log.info("%s: conectado ao broker", client_id)
        if on_connect:
            on_connect(client)

    def _on_disconnect(_client, _userdata, _flags, reason_code, _props):
        log.warning("%s: desconectado do broker (%s)", client_id, reason_code)

    def _on_message(_client, _userdata, msg):
        if on_message:
            try:
                on_message(msg.topic, msg.payload.decode("utf-8", errors="replace"))
            except Exception:  # a thread de rede não pode morrer por causa de uma mensagem
                log.exception("%s: erro ao tratar %s", client_id, msg.topic)

    c.on_connect, c.on_disconnect, c.on_message = _on_connect, _on_disconnect, _on_message
    host, port = broker_address()
    c.connect_async(host, port, keepalive=10)
    c.loop_start()
    return c


def publish(c: mqtt.Client, topic: str, payload: str, qos: int = 0, retain: bool = False) -> bool:
    if not c.is_connected():
        return False
    return c.publish(topic, payload, qos=qos, retain=retain).rc == mqtt.MQTT_ERR_SUCCESS

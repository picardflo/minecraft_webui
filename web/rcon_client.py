import asyncio
import struct


async def execute_rcon(host: str, port: int, password: str, command: str) -> str:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=5
        )
        try:
            await _send(writer, 1, 3, password)
            resp_id, resp_type, _ = await asyncio.wait_for(_recv(reader), timeout=5)
            if resp_id == -1:
                return "Erreur RCON : mot de passe incorrect"

            await _send(writer, 2, 2, command)
            _, _, payload = await asyncio.wait_for(_recv(reader), timeout=5)
            return payload or "(pas de réponse)"
        finally:
            writer.close()
            await writer.wait_closed()
    except asyncio.TimeoutError:
        return "Erreur RCON : timeout (serveur injoignable ?)"
    except Exception as e:
        return f"Erreur RCON : {e}"


async def _send(writer, req_id: int, req_type: int, payload: str) -> None:
    data = payload.encode("utf-8") + b"\x00\x00"
    packet = struct.pack("<iii", 4 + 4 + len(data), req_id, req_type) + data
    writer.write(packet)
    await writer.drain()


async def _recv(reader) -> tuple[int, int, str]:
    header = await reader.readexactly(12)
    length, req_id, req_type = struct.unpack("<iii", header)
    body = await reader.readexactly(length - 8)
    payload = body[:-2].decode("utf-8", errors="replace")
    return req_id, req_type, payload

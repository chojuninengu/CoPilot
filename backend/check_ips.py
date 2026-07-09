import asyncio
from sqlalchemy.future import select
from app.db.db_session import sessionmaker
from app.db.universal_models import Agents
from app.connectors.velociraptor.services.agents import get_clients_velociraptor

async def main():
    async with sessionmaker() as session:
        result = await session.execute(select(Agents))
        agents = result.scalars().all()
        for a in agents:
            print(f"Wazuh Agent DB: {a.hostname} (IP: {a.ip_address})")
        
        clients = await get_clients_velociraptor()
        for c in clients.get("items", []):
            print(f"Velociraptor Client: {c.os_info.hostname} (IP: {c.last_ip})")

asyncio.run(main())

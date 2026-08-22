"""
Base Agent — Bus-connected worker template.

Every specialist agent inherits from this class.
Agents are long-lived workers that subscribe to the Shared Memory Bus
and listen for tasks continuously. They are NOT created per-request.

Lifecycle:
    1. start()    → subscribe to bus
    2. run()      → async loop: receive message → handle → publish result
    3. handle()   → dispatch to process(), manage retries
    4. process()  → abstract: each specialist implements this
"""
from abc import ABC, abstractmethod
from models.messages import AgentMessage
from motor.motor_asyncio import AsyncIOMotorDatabase
import asyncio
import time


# Result status constants
SUCCESS = "SUCCESS"
BUSINESS_EXCEPTION = "BUSINESS_EXCEPTION"
TECHNICAL_FAILURE = "TECHNICAL_FAILURE"

MAX_RETRIES = 2


class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name
        self._bus = None
        self._db_getter = None  # Function that returns the DB
        self._running = False

    def set_bus(self, bus):
        """Connect this agent to the shared memory bus."""
        self._bus = bus

    def set_db_getter(self, db_getter):
        """Set the database getter function."""
        self._db_getter = db_getter

    @property
    def db(self):
        """Get the database instance."""
        if self._db_getter:
            return self._db_getter()
        return None

    async def start(self):
        """Subscribe to the bus and start the listening loop."""
        if self._bus:
            self._bus.subscribe(self.name)
            self._running = True
            # Start the listener as a background task
            asyncio.create_task(self._run_loop())
            print(f"  [+] Agent [{self.name}] started and listening on bus")

    async def _run_loop(self):
        """Main async loop — continuously listen for messages on the bus."""
        while self._running:
            try:
                message = await self._bus.receive(self.name, timeout=300)
                if message:
                    await self._handle(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{self.name}] Loop error: {e}")
                await asyncio.sleep(1)

    async def _handle(self, raw_message: dict):
        """
        Handle an incoming message from the bus.
        Includes retry logic for technical failures.
        """
        try:
            input_message = AgentMessage(**raw_message)
        except Exception as e:
            print(f"[{self.name}] Bad message format: {e}")
            return

        retry_count = 0
        last_error = None

        while retry_count <= MAX_RETRIES:
            start_time = time.time()
            try:
                result = await self.process(input_message, self.db)
                execution_time = time.time() - start_time

                # Enrich result metadata
                result.metadata["execution_time"] = round(execution_time, 3)
                result.metadata["retry_count"] = retry_count
                result.metadata["parent_message_id"] = input_message.message_id
                result.status = "completed"

                # Publish result back to bus
                if self._bus:
                    await self._bus.publish(result.to_bus_dict())
                return

            except Exception as e:
                execution_time = time.time() - start_time
                last_error = str(e)
                retry_count += 1

                if retry_count <= MAX_RETRIES:
                    print(f"[{self.name}] Technical failure (attempt {retry_count}/{MAX_RETRIES + 1}): {e}")
                    await asyncio.sleep(0.5 * retry_count)  # Backoff
                else:
                    # All retries exhausted — publish error
                    error_msg = AgentMessage(
                        workflow_id=input_message.workflow_id,
                        from_agent=self.name,
                        to_agent="orchestrator",
                        message_type="error",
                        status="failed",
                        payload={
                            "error": last_error,
                            "result_type": TECHNICAL_FAILURE,
                        },
                        metadata={
                            "execution_time": round(execution_time, 3),
                            "retry_count": retry_count,
                            "parent_message_id": input_message.message_id,
                        }
                    )
                    if self._bus:
                        await self._bus.publish(error_msg.to_bus_dict())

    async def execute(self, input_message: AgentMessage, db) -> AgentMessage:
        """
        Direct execution method (bypass bus).
        Used by orchestrator for synchronous workflow execution.
        """
        start_time = time.time()
        try:
            result = await self.process(input_message, db)
            execution_time = time.time() - start_time
            result.metadata["execution_time"] = round(execution_time, 3)
            result.status = "completed"
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            return AgentMessage(
                workflow_id=input_message.workflow_id,
                from_agent=self.name,
                to_agent="orchestrator",
                message_type="error",
                status="failed",
                payload={"error": str(e), "result_type": TECHNICAL_FAILURE},
                metadata={"execution_time": round(execution_time, 3)}
            )

    @abstractmethod
    async def process(self, input_message: AgentMessage, db) -> AgentMessage:
        """Core business logic — implemented by each specialist agent."""
        pass

    def stop(self):
        """Stop the agent's listening loop."""
        self._running = False

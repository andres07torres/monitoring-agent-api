from sqlalchemy import Column, Integer, Float, BigInteger
from .database import Base

class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(BigInteger, index=True)
    cpu_percent = Column(Float)
    ram_percent = Column(Float)

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker


SESSION_TTL_SECONDS = 8 * 60 * 60
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-jwt-secret")
JWT_ALGORITHM = "HS256"
SUPER_ADMIN_USERNAME = "superadmin"
SUPER_ADMIN_PASSWORD = "93417@Iphone"
SUPER_ADMIN_ROLE = "admin"
PUBLIC_PATHS = {"/docs", "/openapi.json", "/redoc"}


# ================= Database setup =================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./payroll.db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    username = Column(String, primary_key=True, index=True)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    empId = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=True)
    monthlySalary = Column(Float, nullable=False, default=0)
    visaTotal = Column(Float, nullable=False, default=0)
    joinDate = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="Active")
    openingBalance = Column(Float, nullable=False, default=0)

    transactions = relationship("Transaction", back_populates="employee")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    txId = Column(String, unique=True, index=True, nullable=False)
    date = Column(DateTime, nullable=False)
    empId = Column(String, ForeignKey("employees.empId"), nullable=False, index=True)
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    site = Column(String, nullable=True)
    paidBy = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    createdBy = Column(String, nullable=False, default="web")
    runningBalance = Column(Float, nullable=True)

    employee = relationship("Employee", back_populates="transactions")


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"
    __table_args__ = (UniqueConstraint("empId", "month", name="uq_timesheet_emp_month"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    empId = Column(String, ForeignKey("employees.empId"), nullable=False, index=True)
    month = Column(String, nullable=False, index=True)  # YYYY-MM
    totalHours = Column(Float, nullable=False, default=0)
    totalOvertime = Column(Float, nullable=False, default=0)
    entryCount = Column(Integer, nullable=False, default=0)
    itemsJson = Column(Text, nullable=False, default="[]")
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedBy = Column(String, nullable=False, default="web")


class PurchaseOrderEntry(Base):
    __tablename__ = "purchase_order_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    poId = Column(String, unique=True, index=True, nullable=False)
    purchaseOrderDate = Column(String, nullable=False, default="")
    endType = Column(String, nullable=False, default="date")
    endDate = Column(String, nullable=False, default="")
    plateNo = Column(String, nullable=False, default="")
    model = Column(String, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    location = Column(String, nullable=False, default="")
    monthlyRent = Column(String, nullable=False, default="")
    companyName = Column(String, nullable=False, default="")
    lpoLink = Column(Text, nullable=False, default="")
    operatorName = Column(String, nullable=False, default="")
    paymentSchedule = Column(String, nullable=False, default="")
    shift = Column(String, nullable=False, default="")
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedBy = Column(String, nullable=False, default="web")


class PlateDetail(Base):
    __tablename__ = "plate_details"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plateNo = Column(String, unique=True, index=True, nullable=False)
    model = Column(String, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    monthlyRent = Column(String, nullable=False, default="")
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedBy = Column(String, nullable=False, default="web")


class PurchaseOrderCompany(Base):
    __tablename__ = "purchase_order_companies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True, nullable=False)
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedBy = Column(String, nullable=False, default="web")


class MonthlyClosingEntry(Base):
    __tablename__ = "monthly_closing_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mcId = Column(String, unique=True, index=True, nullable=False)
    month = Column(String, nullable=False, index=True, default="")
    totalIncome = Column(Float, nullable=False, default=0)
    operatorSalary = Column(Float, nullable=False, default=0)
    companyExpense = Column(Float, nullable=False, default=0)
    loss = Column(Float, nullable=False, default=0)
    notes = Column(Text, nullable=False, default="")
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedBy = Column(String, nullable=False, default="web")


class ReturnEntry(Base):
    __tablename__ = "return_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    returnId = Column(String, unique=True, index=True, nullable=False)
    purchaseOrderDate = Column(String, nullable=False, default="")
    endDate = Column(String, nullable=False, default="")
    plateNo = Column(String, nullable=False, default="")
    model = Column(String, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    location = Column(String, nullable=False, default="")
    monthlyRent = Column(String, nullable=False, default="")
    companyName = Column(String, nullable=False, default="")
    operatorName = Column(String, nullable=False, default="")
    paymentSchedule = Column(String, nullable=False, default="")
    shift = Column(String, nullable=False, default="")
    createdAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedBy = Column(String, nullable=False, default="web")


class TaxInvoiceState(Base):
    __tablename__ = "tax_invoice_state"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    stateKey = Column(String, unique=True, index=True, nullable=False, default="default")
    fileName = Column(String, nullable=False, default="Tax Invoice")
    sheetHtml = Column(Text, nullable=False, default="")
    updatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    updatedBy = Column(String, nullable=False, default="web")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # Add runningBalance column if missing (migration for existing DBs)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN runningBalance REAL"))
            conn.commit()
    except Exception:
        pass  # Column already exists
    # Add timesheet summary columns if missing (migration for existing DBs)
    for sql in (
        "ALTER TABLE timesheet_entries ADD COLUMN totalHours REAL NOT NULL DEFAULT 0",
        "ALTER TABLE timesheet_entries ADD COLUMN totalOvertime REAL NOT NULL DEFAULT 0",
        "ALTER TABLE timesheet_entries ADD COLUMN entryCount INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception:
            pass  # Column already exists / table not created yet
    # Enable WAL mode for better concurrent access
    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            conn.execute(text("PRAGMA busy_timeout=30000"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()
    except Exception as e:
        # If WAL mode fails, continue without it
        print(f"Warning: Could not enable WAL mode: {e}")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ================= Session handling =================

def _create_session(username: str, role: str) -> Dict[str, Any]:
    now = datetime.utcnow()
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=SESSION_TTL_SECONDS),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": username,
        "role": role,
        "ttlSeconds": SESSION_TTL_SECONDS,
    }


def require_session_(token: Optional[str]) -> Dict[str, Any]:
    if not token:
        raise ValueError("Session expired. Please login again.")
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Session expired. Please login again.")
    except jwt.InvalidTokenError:
        raise ValueError("Session expired. Please login again.")

    username = str(payload.get("sub") or "").strip()
    role = str(payload.get("role") or "").strip().lower()
    if not username or not role:
        raise ValueError("Session expired. Please login again.")
    return {"username": username, "role": role}


def require_role_(sess: Dict[str, Any], allowed: List[str]) -> None:
    role = str(sess.get("role", "")).lower()
    if role not in [a.lower() for a in allowed]:
        raise ValueError("Permission denied")


def get_current_session(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    session_query: Optional[str] = Query(None, alias="session"),
) -> Dict[str, Any]:
    """
    FastAPI dependency that resolves the current session either from header
    X-Session-Token or from the ?session= query parameter.
    Raises 401 if the session is invalid or expired.
    """
    bearer_token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization[len("Bearer ") :].strip()

    token = bearer_token or session_token or session_query
    try:
        return require_session_(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


# ================= Helper utilities =================


def normalize_date_(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return datetime.fromtimestamp(val.timestamp())
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    try:
        d = datetime.fromisoformat(str(val).strip())
        return d
    except Exception:
        try:
            d2 = datetime.strptime(str(val).strip(), "%Y-%m-%d")
            return d2
        except Exception:
            return None


def iso_date_(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def resolve_range_(from_str: Optional[str], to_str: Optional[str]) -> Dict[str, str]:
    if not from_str and not to_str:
        now = datetime.utcnow()
        first = date(now.year, now.month, 1)
        if now.month == 12:
            last = date(now.year, 12, 31)
        else:
            first_next = date(now.year, now.month + 1, 1)
            last = first_next - timedelta(days=1)
        return {"from": iso_date_(first), "to": iso_date_(last)}
    if not from_str or not to_str:
        raise ValueError("Provide both from and to, or none.")
    return {"from": from_str, "to": to_str}


def compute_salary_for_range_(monthly_salary: float, from_str: str, to_str: str) -> float:
    if not monthly_salary:
        return 0.0
    start = datetime.fromisoformat(from_str + "T00:00:00")
    end = datetime.fromisoformat(to_str + "T23:59:59")
    if end < start:
        return 0.0

    months = 0
    y = start.year
    m = start.month
    end_y = end.year
    end_m = end.month

    while y < end_y or (y == end_y and m <= end_m):
        months += 1
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months * monthly_salary


def sum_all_visa_deduction_(db: Session, emp_id: str) -> float:
    txs: List[Transaction] = (
        db.query(Transaction)
        .filter(Transaction.empId == emp_id, Transaction.type == "Visa Deduction")
        .all()
    )
    return float(sum(t.amount or 0 for t in txs))


def sum_all_visa_payment_(db: Session, emp_id: str) -> float:
    txs = db.query(Transaction).filter(Transaction.empId == emp_id, Transaction.type == "Visa Payment").all()
    return float(sum(t.amount or 0 for t in txs))


def sum_all_advance_(db: Session, emp_id: str) -> float:
    txs = db.query(Transaction).filter(Transaction.empId == emp_id, Transaction.type == "Advance").all()
    return float(sum(t.amount or 0 for t in txs))


# ================= Core logic (equivalent to Apps Script) =================


def login_(db: Session, username: Optional[str], password: Optional[str]) -> Dict[str, Any]:
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        raise ValueError("Username and password required")

    # Hidden built-in account for emergency admin access.
    if username == SUPER_ADMIN_USERNAME and password == SUPER_ADMIN_PASSWORD:
        return _create_session(SUPER_ADMIN_USERNAME, SUPER_ADMIN_ROLE)

    users = db.query(User).all()
    if len(users) == 0:
        raise ValueError("No users found in Users table")

    user = next((u for u in users if (u.username or "").strip() == username), None)
    if not user or user.password != password:
        raise ValueError("Invalid credentials")

    role = (user.role or "viewer").strip().lower()
    return _create_session(username, role)


def read_employee_params_(
    empId: Optional[str],
    name: Optional[str],
    role: Optional[str],
    monthlySalary: Optional[float],
    visaTotal: Optional[float],
    joinDate: Optional[str],
    status: Optional[str],
    openingBalance: Optional[float],
) -> Dict[str, Any]:
    empId = (empId or "").strip()
    name = (name or "").strip()
    role = (role or "").strip()
    monthlySalary = float(monthlySalary or 0)
    visaTotal = float(visaTotal or 0)
    joinDate = (joinDate or "").strip()
    status = (status or "Active").strip()
    openingBalance = float(openingBalance or 0)

    # empId can be empty when adding a new employee; it will be auto-generated in add_employee_
    if not name:
        raise ValueError("name required")
    if not (monthlySalary >= 0):
        raise ValueError("monthlySalary must be >= 0")
    if not (visaTotal >= 0):
        raise ValueError("visaTotal must be >= 0")
    # openingBalance can be negative; allow any number

    return {
        "empId": empId,
        "name": name,
        "role": role,
        "monthlySalary": monthlySalary,
        "visaTotal": visaTotal,
        "joinDate": joinDate,
        "status": status,
        "openingBalance": openingBalance,
    }


def get_next_employee_id_(db: Session) -> str:
    """Return next employee ID as EMP + (max existing numeric part + 1), zero-padded to 3 digits."""
    ids = [row.empId for row in db.query(Employee.empId).all()]
    nums = []
    for eid in ids:
        if not eid:
            continue
        m = re.search(r"\d+", eid)
        if m:
            nums.append(int(m.group()))
    next_num = max(nums, default=0) + 1
    return f"EMP{next_num:03d}"


def get_employees_(db: Session) -> List[Dict[str, Any]]:
    emps = db.query(Employee).all()
    result: List[Dict[str, Any]] = []
    for e in emps:
        result.append(
            {
                "empId": e.empId,
                "name": e.name,
                "role": e.role,
                "monthlySalary": e.monthlySalary,
                "visaTotal": e.visaTotal,
                "joinDate": iso_date_(e.joinDate) if e.joinDate else "",
                "status": e.status,
                "openingBalance": e.openingBalance,
            }
        )
    return result


def add_employee_(db: Session, emp: Dict[str, Any]) -> None:
    if not (emp.get("empId") or "").strip():
        emp["empId"] = get_next_employee_id_(db)
    existing = db.query(Employee).filter(Employee.empId == emp["empId"]).first()
    if existing:
        raise ValueError(f"Employee already exists: {emp['empId']}")

    join_date_obj: Optional[date] = None
    if emp.get("joinDate"):
        dt = datetime.fromisoformat(emp["joinDate"] + "T00:00:00")
        join_date_obj = dt.date()

    e = Employee(
        empId=emp["empId"],
        name=emp["name"],
        role=emp["role"],
        monthlySalary=emp["monthlySalary"],
        visaTotal=emp["visaTotal"],
        joinDate=join_date_obj,
        status=emp.get("status") or "Active",
        openingBalance=emp.get("openingBalance", 0),
    )
    db.add(e)
    db.commit()


def update_employee_(db: Session, emp: Dict[str, Any]) -> None:
    e: Optional[Employee] = db.query(Employee).filter(Employee.empId == emp["empId"]).first()
    if not e:
        raise ValueError(f"Employee not found: {emp['empId']}")

    e.name = emp["name"]
    e.role = emp["role"]
    e.monthlySalary = emp["monthlySalary"]
    e.visaTotal = emp["visaTotal"]
    e.status = emp.get("status") or "Active"
    e.openingBalance = emp.get("openingBalance", 0)

    if emp.get("joinDate"):
        dt = datetime.fromisoformat(emp["joinDate"] + "T00:00:00")
        e.joinDate = dt.date()
    else:
        e.joinDate = None

    db.commit()


def set_employee_status_(db: Session, emp_id: str, status: str) -> Dict[str, Any]:
    e: Optional[Employee] = db.query(Employee).filter(Employee.empId == emp_id).first()
    if not e:
        raise ValueError(f"Employee not found: {emp_id}")
    e.status = status
    db.commit()
    return {"empId": emp_id, "status": status}


def delete_employee_(db: Session, emp_id: str) -> Dict[str, Any]:
    e: Optional[Employee] = db.query(Employee).filter(Employee.empId == emp_id).first()
    if not e:
        raise ValueError(f"Employee not found: {emp_id}")

    tx_count = db.query(Transaction).filter(Transaction.empId == emp_id).count()
    if tx_count > 0:
        raise ValueError(
            f"Cannot delete employee {emp_id}. Remove related transactions first ({tx_count} found)."
        )

    db.delete(e)
    db.commit()
    return {"empId": emp_id, "deleted": True}


def _tx_balance_effect(type_: str, amount: float) -> float:
    """Return the change to running balance (company owes employee) for one transaction."""
    type_ = (type_ or "").strip()
    amt = float(amount or 0)
    if type_ in ("Salary", "Overtime"):
        return amt
    if type_ == "Adjustment":
        return amt  # can be positive or negative
    if type_ in ("Salary Paid", "Advance", "Visa Payment", "Visa Deduction"):
        return -amt
    return 0.0


def _is_deduction(type_: str, amount: float) -> bool:
    """True if transaction is a deduction (show after earnings on same date)."""
    type_ = (type_ or "").strip()
    amt = float(amount or 0)
    if type_ in ("Salary", "Overtime"):
        return False
    if type_ == "Adjustment":
        return amt <= 0
    if type_ in ("Salary Paid", "Advance", "Visa Payment", "Visa Deduction"):
        return True
    return True


def _balance_before_tx(
    db: Session, emp_id: str, before_date: datetime, before_tx_id: str, opening_balance: float
) -> float:
    """Running balance for employee after all transactions strictly before (before_date, before_tx_id)."""
    rows = (
        db.query(Transaction)
        .filter(Transaction.empId == emp_id)
        .order_by(Transaction.date, Transaction.txId)
        .all()
    )
    balance = float(opening_balance or 0)
    for r in rows:
        # Include only transactions strictly before this (date, txId)
        if (r.date, r.txId or "") < (before_date, before_tx_id):
            balance += _tx_balance_effect(r.type, r.amount)
        else:
            break
    return balance


def get_transactions_(
    db: Session, emp_id: Optional[str], from_str: Optional[str], to_str: Optional[str]
) -> List[Dict[str, Any]]:
    q = db.query(Transaction, Employee).join(Employee, Employee.empId == Transaction.empId)
    if emp_id:
        q = q.filter(Transaction.empId == emp_id)

    rows = q.all()  # list of (Transaction, Employee)

    from_d = datetime.fromisoformat(from_str + "T00:00:00") if from_str else None
    to_d = datetime.fromisoformat(to_str + "T23:59:59") if to_str else None

    filtered: List[tuple[Transaction, Employee]] = []
    for t, e in rows:
        d = normalize_date_(t.date)
        if not d:
            continue
        if from_d and d < from_d:
            continue
        if to_d and d > to_d:
            continue
        filtered.append((t, e))

    # Same date: earnings first, then deductions; preserve positions within each group (by txId)
    filtered.sort(
        key=lambda pair: (
            normalize_date_(pair[0].date) or datetime.fromtimestamp(0),
            1 if _is_deduction(pair[0].type, pair[0].amount) else 0,
            pair[0].txId or "",
        )
    )

    # Compute running balance in display order (earnings first, then deductions per date)
    balance_by_emp: Dict[str, float] = {}
    result: List[Dict[str, Any]] = []
    for t, e in filtered:
        eid = t.empId
        if eid not in balance_by_emp:
            balance_by_emp[eid] = float(e.openingBalance or 0)
        balance_by_emp[eid] += _tx_balance_effect(t.type, t.amount)
        rb = round(balance_by_emp[eid], 2)
        result.append(
            {
                "txId": t.txId,
                "date": t.date.isoformat(),
                "empId": t.empId,
                "empName": e.name,
                "type": t.type,
                "amount": t.amount,
                "site": t.site,
                "paidBy": t.paidBy,
                "notes": t.notes,
                "createdAt": t.createdAt.isoformat() if t.createdAt else None,
                "createdBy": t.createdBy,
                "runningBalance": rb,
            }
        )
    return result


def add_transaction_(
    db: Session,
    tx: Dict[str, Any],
    created_by: str,
    sequence: Optional[int] = None,
    base_ts_ms: Optional[int] = None,
) -> Dict[str, Any]:
    date_str = (tx.get("date") or "").strip()
    emp_id = (tx.get("empId") or "").strip()
    type_ = (tx.get("type") or "").strip()
    amount = float(tx.get("amount") or 0)

    if not date_str:
        raise ValueError("date is required (YYYY-MM-DD)")
    if not emp_id:
        raise ValueError("empId is required")
    if not type_:
        raise ValueError("type is required")

    allowed = ["Overtime", "Advance", "Visa Deduction", "Visa Payment", "Adjustment", "Salary Paid", "Salary"]
    if type_ not in allowed:
        raise ValueError(f"Invalid type: {type_}")

    if type_ == "Adjustment":
        if amount == 0:
            raise ValueError("Adjustment amount cannot be 0")
    else:
        if amount <= 0:
            raise ValueError("amount must be a positive number")

    emp = db.query(Employee).filter(Employee.empId == emp_id).first()
    if not emp:
        raise ValueError(f"Employee not found: {emp_id}")

    now = datetime.utcnow()
    dt = datetime.fromisoformat(date_str + "T00:00:00")
    dt = dt.replace(
        hour=now.hour,
        minute=now.minute,
        second=now.second,
        microsecond=now.microsecond,
    )

    ts = base_ts_ms if (sequence is not None and base_ts_ms is not None) else int(now.timestamp() * 1000)
    if sequence is not None:
        tx_id = f"TX-{ts}-{sequence:04d}-{uuid.uuid4().hex[:3]}"
    else:
        tx_id = f"TX-{ts}-{uuid.uuid4().hex[:3]}"

    # Compute running balance at insert: one complete entry then move to next (no summing)
    opening = float(emp.openingBalance or 0)
    balance_before = _balance_before_tx(db, emp_id, dt, tx_id, opening)
    balance_after = balance_before + _tx_balance_effect(type_, amount)

    t = Transaction(
        txId=tx_id,
        date=dt,
        empId=emp_id,
        type=type_,
        amount=amount,
        site=(tx.get("site") or "").strip(),
        paidBy=(tx.get("paidBy") or "").strip(),
        notes=(tx.get("notes") or "").strip(),
        createdAt=now,
        createdBy=(created_by or "web").strip(),
        runningBalance=round(balance_after, 2),
    )
    
    # Retry logic for database locks
    max_retries = 5
    retry_delay = 0.1
    for attempt in range(max_retries):
        try:
            db.add(t)
            db.commit()
            db.refresh(t)
            break
        except Exception as e:
            db.rollback()
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
            raise ValueError(f"Failed to save transaction after {max_retries} attempts: {str(e)}") from e

    return {
        "txId": tx_id,
        "date": t.date.isoformat(),
        "empId": emp_id,
        "type": type_,
        "amount": amount,
    }


def delete_transaction_(db: Session, tx_id: str) -> Dict[str, Any]:
    """Delete a transaction by txId. Returns the deleted txId on success."""
    tx = db.query(Transaction).filter(Transaction.txId == tx_id).first()
    if not tx:
        raise ValueError(f"Transaction not found: {tx_id}")
    emp_id = tx.empId
    deleted_date, deleted_tx_id = tx.date, tx.txId
    db.delete(tx)
    db.flush()  # so we can query without the deleted row
    # Clear stored runningBalance for later rows so they recompute when read
    all_after = (
        db.query(Transaction)
        .filter(Transaction.empId == emp_id)
        .order_by(Transaction.date, Transaction.txId)
        .all()
    )
    for t in all_after:
        if (t.date, t.txId or "") > (deleted_date, deleted_tx_id):
            t.runningBalance = None
    db.commit()
    return {"txId": tx_id, "deleted": True}


def update_transaction_details_(
    db: Session, tx_id: str, site: Optional[str], paid_by: Optional[str], notes: Optional[str]
) -> Dict[str, Any]:
    """Update a transaction's site, paidBy, and notes by txId. Returns the updated transaction summary."""
    tx = db.query(Transaction).filter(Transaction.txId == tx_id).first()
    if not tx:
        raise ValueError(f"Transaction not found: {tx_id}")
    if site is not None:
        tx.site = (site or "").strip()
    if paid_by is not None:
        tx.paidBy = (paid_by or "").strip()
    if notes is not None:
        tx.notes = (notes or "").strip()
    db.commit()
    db.refresh(tx)
    return {
        "txId": tx.txId,
        "site": tx.site,
        "paidBy": tx.paidBy,
        "notes": tx.notes,
    }


def normalize_month_(month_str: str) -> str:
    month_clean = (month_str or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", month_clean):
        raise ValueError("month is required in YYYY-MM format")
    month_num = int(month_clean.split("-")[1])
    if month_num < 1 or month_num > 12:
        raise ValueError("Invalid month value")
    return month_clean


def summarize_timesheet_items_(items: Any) -> Dict[str, Any]:
    if not isinstance(items, list):
        return {"totalHours": 0.0, "totalOvertime": 0.0, "entryCount": 0}
    total_hours = 0.0
    total_ot = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        hours = float(it.get("hours") or 0)
        overtime = float(it.get("overtime") or 0)
        if hours > 0:
            total_hours += hours
        if overtime > 0:
            total_ot += overtime
    return {
        "totalHours": round(total_hours, 2),
        "totalOvertime": round(total_ot, 2),
        "entryCount": len(items),
    }


def sanitize_timesheet_items_(items: Any, month_str: str) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("Timesheet items must be a list")
    cleaned: List[Dict[str, Any]] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"Invalid timesheet item at index {idx}")
        date_str = str(it.get("date") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            raise ValueError(f"Invalid date in timesheet item at index {idx}")
        if not date_str.startswith(month_str + "-"):
            raise ValueError(f"Date {date_str} does not belong to month {month_str}")
        try:
            datetime.fromisoformat(date_str + "T00:00:00")
        except Exception as exc:
            raise ValueError(f"Invalid date in timesheet item at index {idx}") from exc
        hours = float(it.get("hours") or 0)
        overtime = float(it.get("overtime") or 0)
        if hours < 0 or overtime < 0:
            raise ValueError(f"Hours and overtime must be >= 0 (item index {idx})")
        cleaned.append(
            {
                "date": date_str,
                "hours": round(hours, 2),
                "overtime": round(overtime, 2),
            }
        )
    cleaned.sort(key=lambda row: row["date"])
    return cleaned


def get_timesheet_(db: Session, emp_id: str, month_str: str) -> Dict[str, Any]:
    emp_clean = (emp_id or "").strip()
    if not emp_clean:
        raise ValueError("empId is required")
    month_clean = normalize_month_(month_str)
    emp = db.query(Employee).filter(Employee.empId == emp_clean).first()
    if not emp:
        raise ValueError(f"Employee not found: {emp_clean}")

    row = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.empId == emp_clean, TimesheetEntry.month == month_clean)
        .first()
    )
    if not row:
        return {
            "empId": emp_clean,
            "empName": emp.name,
            "month": month_clean,
            "totalHours": 0.0,
            "totalOvertime": 0.0,
            "entryCount": 0,
            "items": [],
            "exists": False,
        }

    items: List[Dict[str, Any]] = []
    try:
        parsed = json.loads(row.itemsJson or "[]")
        if isinstance(parsed, list):
            items = parsed
    except Exception:
        items = []

    # Backward compatibility: if legacy rows only had itemsJson, derive totals.
    total_hours = float(row.totalHours or 0)
    total_ot = float(row.totalOvertime or 0)
    entry_count = int(row.entryCount or 0)
    if (total_hours == 0 and total_ot == 0 and entry_count == 0) and len(items) > 0:
        summary = summarize_timesheet_items_(items)
        total_hours = float(summary["totalHours"])
        total_ot = float(summary["totalOvertime"])
        entry_count = int(summary["entryCount"])

    return {
        "empId": emp_clean,
        "empName": emp.name,
        "month": month_clean,
        "totalHours": round(total_hours, 2),
        "totalOvertime": round(total_ot, 2),
        "entryCount": entry_count,
        "items": items,
        "exists": True,
        "updatedAt": row.updatedAt.isoformat() if row.updatedAt else None,
        "updatedBy": row.updatedBy,
    }


def save_timesheet_(
    db: Session,
    emp_id: str,
    month_str: str,
    total_hours: float,
    total_overtime: float,
    entry_count: int,
    items: Optional[List[Dict[str, Any]]],
    updated_by: str,
) -> Dict[str, Any]:
    emp_clean = (emp_id or "").strip()
    if not emp_clean:
        raise ValueError("empId is required")
    month_clean = normalize_month_(month_str)
    emp = db.query(Employee).filter(Employee.empId == emp_clean).first()
    if not emp:
        raise ValueError(f"Employee not found: {emp_clean}")

    hours_clean = round(float(total_hours or 0), 2)
    ot_clean = round(float(total_overtime or 0), 2)
    count_clean = int(entry_count or 0)
    if hours_clean < 0 or ot_clean < 0 or count_clean < 0:
        raise ValueError("Timesheet totals/count must be >= 0")
    if hours_clean <= 0 and ot_clean <= 0:
        raise ValueError("Blank sheet cannot be saved. Enter hours or overtime first.")

    items_clean: List[Dict[str, Any]] = []
    if isinstance(items, list):
        items_clean = sanitize_timesheet_items_(items, month_clean)
        summary = summarize_timesheet_items_(items_clean)
        hours_clean = float(summary["totalHours"])
        ot_clean = float(summary["totalOvertime"])
        count_clean = int(summary["entryCount"])
        if hours_clean <= 0 and ot_clean <= 0:
            raise ValueError("Blank sheet cannot be saved. Enter hours or overtime first.")

    now = datetime.utcnow()
    row = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.empId == emp_clean, TimesheetEntry.month == month_clean)
        .first()
    )
    if not row:
        row = TimesheetEntry(
            empId=emp_clean,
            month=month_clean,
            totalHours=hours_clean,
            totalOvertime=ot_clean,
            entryCount=count_clean,
            itemsJson=json.dumps(items_clean, separators=(",", ":")),
            createdAt=now,
            updatedAt=now,
            updatedBy=(updated_by or "web").strip(),
        )
        db.add(row)
    else:
        row.totalHours = hours_clean
        row.totalOvertime = ot_clean
        row.entryCount = count_clean
        row.itemsJson = json.dumps(items_clean, separators=(",", ":"))
        row.updatedAt = now
        row.updatedBy = (updated_by or "web").strip()

    db.commit()
    db.refresh(row)
    return {
        "empId": emp_clean,
        "empName": emp.name,
        "month": month_clean,
        "totalHours": round(float(row.totalHours or 0), 2),
        "totalOvertime": round(float(row.totalOvertime or 0), 2),
        "entryCount": int(row.entryCount or 0),
        "updatedAt": row.updatedAt.isoformat() if row.updatedAt else None,
        "updatedBy": row.updatedBy,
    }


def delete_timesheet_(db: Session, emp_id: str, month_str: str) -> Dict[str, Any]:
    emp_clean = (emp_id or "").strip()
    if not emp_clean:
        raise ValueError("empId is required")
    month_clean = normalize_month_(month_str)

    row = (
        db.query(TimesheetEntry)
        .filter(TimesheetEntry.empId == emp_clean, TimesheetEntry.month == month_clean)
        .first()
    )
    if not row:
        return {"empId": emp_clean, "month": month_clean, "deleted": False}

    db.delete(row)
    db.commit()
    return {"empId": emp_clean, "month": month_clean, "deleted": True}


def list_timesheets_by_month_(db: Session, month_str: str) -> Dict[str, Any]:
    month_clean = normalize_month_(month_str)
    rows = (
        db.query(TimesheetEntry, Employee)
        .join(Employee, Employee.empId == TimesheetEntry.empId)
        .filter(TimesheetEntry.month == month_clean)
        .order_by(TimesheetEntry.empId.asc())
        .all()
    )

    items: List[Dict[str, Any]] = []
    for t, e in rows:
        total_hours = float(t.totalHours or 0)
        total_ot = float(t.totalOvertime or 0)
        entry_count = int(t.entryCount or 0)

        # Backward compatibility for legacy rows.
        if (total_hours == 0 and total_ot == 0 and entry_count == 0) and (t.itemsJson or "").strip():
            try:
                legacy_items = json.loads(t.itemsJson or "[]")
            except Exception:
                legacy_items = []
            summary = summarize_timesheet_items_(legacy_items)
            total_hours = float(summary["totalHours"])
            total_ot = float(summary["totalOvertime"])
            entry_count = int(summary["entryCount"])

        items.append(
            {
                "empId": t.empId,
                "empName": e.name if e else "",
                "month": t.month,
                "totalHours": round(total_hours, 2),
                "totalOvertime": round(total_ot, 2),
                "entryCount": entry_count,
                "updatedAt": t.updatedAt.isoformat() if t.updatedAt else None,
                "updatedBy": t.updatedBy,
            }
        )

    return {"month": month_clean, "items": items}


def _decode_items_b64_json_(items_b64: Optional[str]) -> Any:
    b64 = (items_b64 or "").strip()
    if not b64:
        return None
    try:
        missing_padding = len(b64) % 4
        if missing_padding:
            b64 += "=" * (4 - missing_padding)
        decoded = base64.urlsafe_b64decode(b64.encode("utf-8"))
        json_str = decoded.decode("utf-8")
        return json.loads(json_str)
    except Exception as exc:
        raise ValueError(f"Failed to decode items_b64: {exc}") from exc


def list_purchase_orders_(db: Session) -> List[Dict[str, Any]]:
    rows = db.query(PurchaseOrderEntry).order_by(PurchaseOrderEntry.id.asc()).all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.poId,
                "purchaseOrderDate": r.purchaseOrderDate or "",
                "endType": r.endType or "date",
                "endDate": r.endDate or "",
                "plateNo": r.plateNo or "",
                "model": r.model or "",
                "description": r.description or "",
                "location": r.location or "",
                "monthlyRent": r.monthlyRent or "",
                "companyName": r.companyName or "",
                "lpoLink": r.lpoLink or "",
                "operatorName": r.operatorName or "",
                "paymentSchedule": r.paymentSchedule or "",
                "shift": r.shift or "",
            }
        )
    return out


def upsert_purchase_order_(db: Session, payload: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
    po_id = str(payload.get("id") or "").strip()
    if not po_id:
        raise ValueError("id is required")
    purchase_order_date = str(payload.get("purchaseOrderDate") or "").strip()
    end_type = str(payload.get("endType") or "date").strip() or "date"
    end_date = str(payload.get("endDate") or "").strip()
    company_name = str(payload.get("companyName") or "").strip()
    if not purchase_order_date:
        raise ValueError("purchaseOrderDate is required")
    if end_type not in ("date", "openLpo"):
        raise ValueError("Invalid endType")
    if end_type == "date" and not end_date:
        raise ValueError("endDate is required when endType=date")
    if not company_name:
        raise ValueError("companyName is required")

    row = db.query(PurchaseOrderEntry).filter(PurchaseOrderEntry.poId == po_id).first()
    now = datetime.utcnow()
    if not row:
        row = PurchaseOrderEntry(poId=po_id, createdAt=now)
        db.add(row)
    row.purchaseOrderDate = purchase_order_date
    row.endType = end_type
    row.endDate = end_date if end_type == "date" else ""
    row.plateNo = str(payload.get("plateNo") or "").strip()
    row.model = str(payload.get("model") or "").strip()
    row.description = str(payload.get("description") or "").strip()
    row.location = str(payload.get("location") or "").strip()
    row.monthlyRent = str(payload.get("monthlyRent") or "").strip()
    row.companyName = company_name
    row.lpoLink = str(payload.get("lpoLink") or "").strip()
    row.operatorName = str(payload.get("operatorName") or "").strip()
    row.paymentSchedule = str(payload.get("paymentSchedule") or "").strip()
    row.shift = str(payload.get("shift") or "").strip()
    row.updatedAt = now
    row.updatedBy = (updated_by or "web").strip()
    db.commit()
    return {"id": po_id, "saved": True}


def delete_purchase_order_(db: Session, po_id: str) -> Dict[str, Any]:
    po_id_clean = (po_id or "").strip()
    if not po_id_clean:
        raise ValueError("id is required")
    row = db.query(PurchaseOrderEntry).filter(PurchaseOrderEntry.poId == po_id_clean).first()
    if not row:
        return {"id": po_id_clean, "deleted": False}
    db.delete(row)
    db.commit()
    return {"id": po_id_clean, "deleted": True}


def clear_purchase_orders_(db: Session) -> Dict[str, Any]:
    count = db.query(PurchaseOrderEntry).delete()
    db.commit()
    return {"deletedCount": int(count or 0)}


def list_plate_details_(db: Session) -> List[Dict[str, Any]]:
    rows = db.query(PlateDetail).order_by(PlateDetail.plateNo.asc()).all()
    return [
        {
            "plateNo": r.plateNo or "",
            "model": r.model or "",
            "description": r.description or "",
            "monthlyRent": r.monthlyRent or "",
        }
        for r in rows
    ]


def replace_plate_details_(db: Session, items: Any, updated_by: str) -> Dict[str, Any]:
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    cleaned: List[Dict[str, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        plate_no = str(it.get("plateNo") or "").strip()
        if not plate_no:
            continue
        cleaned.append(
            {
                "plateNo": plate_no,
                "model": str(it.get("model") or "").strip(),
                "description": str(it.get("description") or "").strip(),
                "monthlyRent": str(it.get("monthlyRent") or "").strip(),
            }
        )
    db.query(PlateDetail).delete()
    now = datetime.utcnow()
    for r in cleaned:
        db.add(
            PlateDetail(
                plateNo=r["plateNo"],
                model=r["model"],
                description=r["description"],
                monthlyRent=r["monthlyRent"],
                createdAt=now,
                updatedAt=now,
                updatedBy=(updated_by or "web").strip(),
            )
        )
    db.commit()
    return {"count": len(cleaned)}


def list_purchase_order_companies_(db: Session) -> List[str]:
    rows = db.query(PurchaseOrderCompany).order_by(PurchaseOrderCompany.name.asc()).all()
    return [str(r.name or "").strip() for r in rows if str(r.name or "").strip()]


def add_purchase_order_company_(db: Session, name: str, updated_by: str) -> Dict[str, Any]:
    company = (name or "").strip()
    if not company:
        raise ValueError("name is required")
    row = db.query(PurchaseOrderCompany).filter(PurchaseOrderCompany.name == company).first()
    now = datetime.utcnow()
    if not row:
        row = PurchaseOrderCompany(name=company, createdAt=now)
        db.add(row)
    row.updatedAt = now
    row.updatedBy = (updated_by or "web").strip()
    db.commit()
    return {"name": company, "saved": True}


def replace_purchase_order_companies_(db: Session, items: Any, updated_by: str) -> Dict[str, Any]:
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    names = sorted({str(x or "").strip() for x in items if str(x or "").strip()})
    db.query(PurchaseOrderCompany).delete()
    now = datetime.utcnow()
    for name in names:
        db.add(
            PurchaseOrderCompany(
                name=name,
                createdAt=now,
                updatedAt=now,
                updatedBy=(updated_by or "web").strip(),
            )
        )
    db.commit()
    return {"count": len(names)}


def list_monthly_closing_entries_(db: Session) -> List[Dict[str, Any]]:
    rows = db.query(MonthlyClosingEntry).order_by(MonthlyClosingEntry.month.asc(), MonthlyClosingEntry.id.asc()).all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.mcId,
                "month": r.month or "",
                "totalIncome": float(r.totalIncome or 0),
                "operatorSalary": float(r.operatorSalary or 0),
                "companyExpense": float(r.companyExpense or 0),
                "loss": float(r.loss or 0),
                "notes": r.notes or "",
            }
        )
    return out


def upsert_monthly_closing_entry_(db: Session, payload: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
    mc_id = str(payload.get("id") or "").strip()
    month = str(payload.get("month") or "").strip()
    if not mc_id:
        raise ValueError("id is required")
    if not month:
        raise ValueError("month is required")
    row = db.query(MonthlyClosingEntry).filter(MonthlyClosingEntry.mcId == mc_id).first()
    now = datetime.utcnow()
    if not row:
        row = MonthlyClosingEntry(mcId=mc_id, createdAt=now)
        db.add(row)
    row.month = month
    row.totalIncome = float(payload.get("totalIncome") or 0)
    row.operatorSalary = float(payload.get("operatorSalary") or 0)
    row.companyExpense = float(payload.get("companyExpense") or 0)
    row.loss = float(payload.get("loss") or 0)
    row.notes = str(payload.get("notes") or "").strip()
    row.updatedAt = now
    row.updatedBy = (updated_by or "web").strip()
    db.commit()
    return {"id": mc_id, "saved": True}


def delete_monthly_closing_entry_(db: Session, entry_id: str) -> Dict[str, Any]:
    id_clean = (entry_id or "").strip()
    if not id_clean:
        raise ValueError("id is required")
    row = db.query(MonthlyClosingEntry).filter(MonthlyClosingEntry.mcId == id_clean).first()
    if not row:
        return {"id": id_clean, "deleted": False}
    db.delete(row)
    db.commit()
    return {"id": id_clean, "deleted": True}


def list_return_entries_(db: Session) -> List[Dict[str, Any]]:
    rows = db.query(ReturnEntry).order_by(ReturnEntry.id.asc()).all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.returnId,
                "purchaseOrderDate": r.purchaseOrderDate or "",
                "endDate": r.endDate or "",
                "plateNo": r.plateNo or "",
                "model": r.model or "",
                "description": r.description or "",
                "location": r.location or "",
                "monthlyRent": r.monthlyRent or "",
                "companyName": r.companyName or "",
                "operatorName": r.operatorName or "",
                "paymentSchedule": r.paymentSchedule or "",
                "shift": r.shift or "",
            }
        )
    return out


def upsert_return_entry_(db: Session, payload: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
    return_id = str(payload.get("id") or "").strip()
    purchase_order_date = str(payload.get("purchaseOrderDate") or "").strip()
    end_date = str(payload.get("endDate") or "").strip()
    if not return_id:
        raise ValueError("id is required")
    if not purchase_order_date:
        raise ValueError("purchaseOrderDate is required")
    if not end_date:
        raise ValueError("endDate is required")
    row = db.query(ReturnEntry).filter(ReturnEntry.returnId == return_id).first()
    now = datetime.utcnow()
    if not row:
        row = ReturnEntry(returnId=return_id, createdAt=now)
        db.add(row)
    row.purchaseOrderDate = purchase_order_date
    row.endDate = end_date
    row.plateNo = str(payload.get("plateNo") or "").strip()
    row.model = str(payload.get("model") or "").strip()
    row.description = str(payload.get("description") or "").strip()
    row.location = str(payload.get("location") or "").strip()
    row.monthlyRent = str(payload.get("monthlyRent") or "").strip()
    row.companyName = str(payload.get("companyName") or "").strip()
    row.operatorName = str(payload.get("operatorName") or "").strip()
    row.paymentSchedule = str(payload.get("paymentSchedule") or "").strip()
    row.shift = str(payload.get("shift") or "").strip()
    row.updatedAt = now
    row.updatedBy = (updated_by or "web").strip()
    db.commit()
    return {"id": return_id, "saved": True}


def delete_return_entry_(db: Session, return_id: str) -> Dict[str, Any]:
    id_clean = (return_id or "").strip()
    if not id_clean:
        raise ValueError("id is required")
    row = db.query(ReturnEntry).filter(ReturnEntry.returnId == id_clean).first()
    if not row:
        return {"id": id_clean, "deleted": False}
    db.delete(row)
    db.commit()
    return {"id": id_clean, "deleted": True}


def get_tax_invoice_state_(db: Session) -> Dict[str, Any]:
    row = db.query(TaxInvoiceState).filter(TaxInvoiceState.stateKey == "default").first()
    if not row:
        return {"exists": False, "fileName": "Tax Invoice", "sheetHtml": ""}
    return {
        "exists": True,
        "fileName": row.fileName or "Tax Invoice",
        "sheetHtml": row.sheetHtml or "",
        "updatedAt": row.updatedAt.isoformat() if row.updatedAt else None,
        "updatedBy": row.updatedBy or "web",
    }


def save_tax_invoice_state_(db: Session, file_name: str, sheet_html: str, updated_by: str) -> Dict[str, Any]:
    row = db.query(TaxInvoiceState).filter(TaxInvoiceState.stateKey == "default").first()
    now = datetime.utcnow()
    if not row:
        row = TaxInvoiceState(stateKey="default")
        db.add(row)
    row.fileName = (file_name or "Tax Invoice").strip() or "Tax Invoice"
    row.sheetHtml = sheet_html or ""
    row.updatedAt = now
    row.updatedBy = (updated_by or "web").strip()
    db.commit()
    return {"saved": True, "updatedAt": now.isoformat()}


def get_summary_(db: Session, emp_id: str, from_str: Optional[str], to_str: Optional[str]) -> Dict[str, Any]:
    if not emp_id:
        raise ValueError("empId is required")

    emp = db.query(Employee).filter(Employee.empId == emp_id).first()
    if not emp:
        raise ValueError(f"Employee not found: {emp_id}")

    range_ = resolve_range_(from_str, to_str)
    from_res = range_["from"]
    to_res = range_["to"]

    txs = get_transactions_(db, emp_id, from_res, to_res)

    # Calculate months covered in the period.
    # We use a unit salary of 1.0 to get the number of months, then multiply by profile salary.
    months_covered = compute_salary_for_range_(1.0, from_res, to_res)
    monthly_salary = float(emp.monthlySalary or 0)
    base_salary = months_covered * monthly_salary

    # Calculation rules (balance = what company owes employee):
    # Advance → Employee owes company (–)
    # Visa Payment → Company paid for employee (–)
    # Visa Deduction → Recovery from employee (–, deduct from pay)
    # Salary → Company owes employee (+)
    # Overtime → Company owes employee (+)
    # Salary Paid → Company paid employee (–)
    # Adjustment: positive (+) add to balance, negative (–) subtract

    # Initialize totals
    overtime = 0.0
    salary_entries = 0.0
    adjustment_pos = 0.0
    adjustment_neg = 0.0
    advance = 0.0
    visa_payment = 0.0
    visa_deduction = 0.0
    salary_paid = 0.0

    # Calculate period totals
    for t in txs:
        type_ = (t.get("type") or "").strip()
        amt = float(t.get("amount") or 0)
        if type_ == "Overtime":
            overtime += amt
        elif type_ == "Salary":
            salary_entries += amt
        elif type_ == "Adjustment":
            if amt > 0:
                adjustment_pos += amt
            else:
                adjustment_neg += abs(amt)
        elif type_ == "Advance":
            advance += amt
        elif type_ == "Visa Payment":
            visa_payment += amt
        elif type_ == "Visa Deduction":
            visa_deduction += amt
        elif type_ == "Salary Paid":
            salary_paid += amt

    # Earnings: company owes employee (+).
    # - Base salary always comes from employee profile (monthlySalary * months in range)
    # - Overtime and positive adjustments are also earnings.
    # Salary "entries" are *not* used here to avoid double-counting.
    earnings = base_salary + overtime + adjustment_pos

    # Deductions: employee owes / company paid (–)
    # - Advances, Visa payments/deductions, and negative adjustments reduce pay.
    # Note: Visa details are shown in the Visa tab, but still included in deductions for payroll calculation.
    deductions = advance + visa_payment + visa_deduction + adjustment_neg

    # Calculate payable salary for the period and remaining payable after payments.
    payable_salary = earnings - deductions
    remaining_payable = payable_salary - salary_paid

    # All‑time calculations (for dashboard widgets)
    unsettled_advance_all_time = sum_all_advance_(db, emp_id)

    # Visa dashboard semantics:
    # - "Visa Payment" comes from employee profile (visaTotal) – total visa cost company paid.
    # - "Visa Deduction" is the sum of all Visa Deduction transactions (all time).
    # - "Remaining Visa Payment" = Visa Payment - Visa Deduction.
    visa_payment_profile = float(emp.visaTotal or 0)
    visa_deducted_all_time = sum_all_visa_deduction_(db, emp_id)
    visa_remaining = visa_payment_profile - visa_deducted_all_time

    employee_dict = {
        "empId": emp.empId,
        "name": emp.name,
        "role": emp.role,
        "monthlySalary": emp.monthlySalary,
        "visaTotal": emp.visaTotal,
        "joinDate": iso_date_(emp.joinDate) if emp.joinDate else "",
        "status": emp.status,
        "openingBalance": emp.openingBalance,
    }

    # Shape of the summary object is designed for the Dashboard.
    # Extra compatibility fields are included so existing frontends continue to work.
    return {
        "employee": employee_dict,
        "period": {"from": from_res, "to": to_res},
        "totals": {
            "baseSalary": base_salary,
            "overtime": overtime,
            "adjustmentPos": adjustment_pos,
            "adjustmentNeg": adjustment_neg,
            "adjustment": adjustment_pos - adjustment_neg,
            "advance": advance,
            "visaPayment": visa_payment_profile,  # from employee profile (visaTotal)
            "visaDeduction": visa_deducted_all_time,  # all-time Visa Deduction transactions
            "visaRemaining": visa_remaining,  # Visa Payment - Visa Deduction
            "salaryPaid": salary_paid,
        },
        # High‑level figures used on Dashboard
        "earnings": earnings,
        "deductions": deductions,
        "payableSalary": payable_salary,
        "remainingPayable": remaining_payable,
        # Dashboard aliases
        "netPayable": remaining_payable,
        "openingBalance": float(emp.openingBalance or 0),
        # All‑time helpers
        "unsettledAdvanceAllTime": unsettled_advance_all_time,
        # Visa block for Dashboard
        "visa": {
            "paymentFromProfile": visa_payment_profile,
            "deductedAllTime": visa_deducted_all_time,
            "remaining": visa_remaining,
        },
        # Flat Visa fields for simple dashboards
        "visaPayment": visa_payment_profile,
        "visaDeduction": visa_deducted_all_time,
        "visaRemaining": visa_remaining,
    }


# ================= Pydantic models for REST endpoints =================


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None


class EmployeeBase(BaseModel):
    name: str
    role: Optional[str] = ""
    monthlySalary: float = 0
    visaTotal: float = 0
    joinDate: Optional[str] = None  # YYYY-MM-DD
    status: Optional[str] = "Active"
    openingBalance: float = 0


class EmployeeCreate(EmployeeBase):
    empId: Optional[str] = None  # optional; auto-generated as max existing + 1 if omitted


class EmployeeUpdate(EmployeeBase):
    pass


class TransactionCreate(BaseModel):
    date: str  # YYYY-MM-DD
    empId: str
    type: str
    amount: float
    site: Optional[str] = ""
    paidBy: Optional[str] = ""
    notes: Optional[str] = ""


class TransactionBulkItem(BaseModel):
    type: str
    amount: float
    notes: Optional[str] = ""


class TransactionBulkCreate(BaseModel):
    empId: str
    date: str  # YYYY-MM-DD
    site: Optional[str] = ""
    paidBy: Optional[str] = ""
    items: List[TransactionBulkItem]


class TransactionDetailsUpdate(BaseModel):
    """Update only site, paidBy, and notes for a transaction."""
    site: Optional[str] = None
    paidBy: Optional[str] = None
    notes: Optional[str] = None


class TaxInvoiceStatePayload(BaseModel):
    fileName: str = "Tax Invoice"
    sheetHtml: str = ""


# ================= FastAPI app & routing =================


app = FastAPI(title="Payroll System API (FastAPI)")

# Allow browser frontends (file:// or other ports) to call this API.
# For development we allow all origins; tighten this if you deploy publicly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://payroll-system-production-9ef7.up.railway.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    # Keep your existing session/login checks here if you enforce auth globally.
    return await call_next(request)


# ----- REST-style endpoints -----


@app.post("/auth/login")
def api_login(payload: LoginRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Login endpoint (body-based). Use POST so password is not sent in URL.
    """
    try:
        username = (payload.username or "").strip()
        password = payload.password or ""
        if not username or not password:
            return {"ok": False, "error": "Username and password are required"}
        data = login_(db, username, password)
        return {"ok": True, "data": data}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Login failed: {str(exc)}"}


@app.post("/auth/seed-admin")
def api_seed_admin(db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        existing = db.query(User).first()
        if existing:
            return {"ok": False, "error": "Users already exist"}

        user = User(username="admin", password="admin123", role="admin")
        db.add(user)
        db.commit()
        return {"ok": True, "message": "Admin created"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/auth/ping")
def api_ping(sess: Dict[str, Any] = Depends(get_current_session)) -> Dict[str, Any]:
    """
    Simple health/auth check using the current session.
    """
    return {
        "ok": True,
        "data": {"message": "pong", "user": sess["username"], "role": sess["role"]},
    }


@app.get("/users")
def list_users(
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    List all users (admin only). Passwords are returned as masked (*******).
    """
    try:
        require_role_(sess, ["admin"])
        users = db.query(User).filter(User.username != SUPER_ADMIN_USERNAME).all()
        data = [
            {
                "username": u.username,
                "role": u.role,
                "password": "*" * 8 if u.password else ""  # Masked password
            }
            for u in users
        ]
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/users")
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
) -> Dict[str, Any]:
    """
    Create a new user.

    - If there are NO users yet, allow creating the very first user without a session
      so you can bootstrap an initial admin.
    - If users already exist, require an admin session (X-Session-Token header).
    """
    try:
        username = (payload.username or "").strip()
        password = (payload.password or "").strip()
        role = (payload.role or "viewer").strip() or "viewer"

        if not username or not password:
            raise ValueError("username and password are required")
        if username == SUPER_ADMIN_USERNAME:
            raise ValueError("This username is reserved")

        users_existing = db.query(User).all()
        if len(users_existing) > 0:
            # Require admin for additional users
            sess = require_session_(x_session_token)
            require_role_(sess, ["admin"])

        existing = db.query(User).filter(User.username == username).first()
        if existing:
            raise ValueError(f"User already exists: {username}")

        user = User(username=username, password=password, role=role)
        db.add(user)
        db.commit()
        return {"ok": True, "data": {"username": user.username, "role": user.role}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/users/{username}")
def get_user(
    username: str,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Get a single user (admin only). Returns masked password by default.
    """
    try:
        require_role_(sess, ["admin"])
        if username == SUPER_ADMIN_USERNAME:
            raise ValueError(f"User not found: {username}")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User not found: {username}")
        return {
            "ok": True,
            "data": {
                "username": user.username,
                "role": user.role,
                "password": "*" * 8 if user.password else ""  # Masked password
            }
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/users/{username}/password")
def get_user_password(
    username: str,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Get a user's actual password (admin only). Use with caution.
    """
    try:
        require_role_(sess, ["admin"])
        if username == SUPER_ADMIN_USERNAME:
            raise ValueError(f"User not found: {username}")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User not found: {username}")
        return {
            "ok": True,
            "data": {
                "username": user.username,
                "password": user.password  # Actual password
            }
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.put("/users/{username}")
def update_user(
    username: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Update a user's password and/or role (admin only).
    """
    try:
        require_role_(sess, ["admin"])
        if username == SUPER_ADMIN_USERNAME:
            raise ValueError(f"User not found: {username}")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError(f"User not found: {username}")
        if payload.password is not None:
            user.password = payload.password
        if payload.role is not None:
            user.role = payload.role
        db.commit()
        return {"ok": True, "data": {"username": user.username, "role": user.role}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/employees")
def list_employees(
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    List all employees (any logged-in user).
    """
    try:
        # Any valid session is allowed; no role restriction
        data = get_employees_(db)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/employees")
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Create a new employee (admin only).
    """
    try:
        require_role_(sess, ["admin"])
        emp = read_employee_params_(
            empId=payload.empId,
            name=payload.name,
            role=payload.role,
            monthlySalary=payload.monthlySalary,
            visaTotal=payload.visaTotal,
            joinDate=payload.joinDate,
            status=payload.status,
            openingBalance=payload.openingBalance,
        )
        add_employee_(db, emp)
        return {"ok": True, "data": emp}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/employees/{emp_id}")
def get_employee(
    emp_id: str,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Get a single employee by empId (any logged-in user).
    """
    try:
        employees = get_employees_(db)
        emp = next((e for e in employees if e["empId"] == emp_id), None)
        if not emp:
            raise ValueError(f"Employee not found: {emp_id}")
        return {"ok": True, "data": emp}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.put("/employees/{emp_id}")
def update_employee(
    emp_id: str,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Update an employee (admin only).
    """
    try:
        require_role_(sess, ["admin"])
        emp = read_employee_params_(
            empId=emp_id,
            name=payload.name,
            role=payload.role,
            monthlySalary=payload.monthlySalary,
            visaTotal=payload.visaTotal,
            joinDate=payload.joinDate,
            status=payload.status,
            openingBalance=payload.openingBalance,
        )
        update_employee_(db, emp)
        return {"ok": True, "data": emp}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.patch("/employees/{emp_id}/status")
def update_employee_status(
    emp_id: str,
    status_payload: Dict[str, str],
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Update the status of an employee (admin only).
    """
    try:
        require_role_(sess, ["admin"])
        new_status = (status_payload.get("status") or "").strip()
        if not new_status:
            raise ValueError("status is required")
        data = set_employee_status_(db, emp_id, new_status)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/employees/{emp_id}/transactions")
def employee_transactions(
    emp_id: str,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Get all transactions for an employee within an optional date range.
    """
    try:
        from_s = (from_ or "").strip() or None
        to_s = (to or "").strip() or None
        data = get_transactions_(db, emp_id, from_s, to_s)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/employees/{emp_id}/summary")
def employee_summary(
    emp_id: str,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Get payroll summary for an employee for a given date range
    (or current month if range is not provided).
    """
    try:
        from_s = (from_ or "").strip() or None
        to_s = (to or "").strip() or None
        data = get_summary_(db, emp_id, from_s, to_s)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/transactions")
def list_transactions(
    empId: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    type: Optional[str] = None,  # noqa: A002
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    List transactions globally, with optional filters.
    """
    try:
        emp_id = (empId or "").strip() or None
        from_s = (from_ or "").strip() or None
        to_s = (to or "").strip() or None
        data = get_transactions_(db, emp_id, from_s, to_s)
        if type:
            ttype = type.strip()
            data = [t for t in data if (t.get("type") or "").strip() == ttype]
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/transactions/{tx_id}")
def get_transaction(
    tx_id: str,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Get a single transaction by txId.
    """
    try:
        tx = db.query(Transaction).filter(Transaction.txId == tx_id).first()
        if not tx:
            raise ValueError(f"Transaction not found: {tx_id}")
        emp = db.query(Employee).filter(Employee.empId == tx.empId).first()
        data = {
            "txId": tx.txId,
            "date": tx.date.isoformat(),
            "empId": tx.empId,
            "empName": emp.name if emp else "",
            "type": tx.type,
            "amount": tx.amount,
            "site": tx.site,
            "paidBy": tx.paidBy,
            "notes": tx.notes,
            "createdAt": tx.createdAt.isoformat() if tx.createdAt else None,
            "createdBy": tx.createdBy,
        }
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.delete("/transactions/{tx_id}")
def delete_transaction(
    tx_id: str,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Delete a transaction by txId (admin or editor only).
    """
    try:
        require_role_(sess, ["admin", "editor"])
        data = delete_transaction_(db, tx_id)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.patch("/transactions/{tx_id}")
def update_transaction_details(
    tx_id: str,
    payload: TransactionDetailsUpdate,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Update a transaction's site, paidBy, and notes (admin or editor only).
    """
    try:
        require_role_(sess, ["admin", "editor"])
        data = update_transaction_details_(
            db, tx_id,
            site=payload.site,
            paid_by=payload.paidBy,
            notes=payload.notes,
        )
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/transactions")
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Create a single transaction (admin or editor).
    """
    try:
        require_role_(sess, ["admin", "editor"])
        tx = {
            "date": payload.date,
            "empId": payload.empId,
            "type": payload.type,
            "amount": payload.amount,
            "site": payload.site,
            "paidBy": payload.paidBy,
            "notes": payload.notes,
        }
        data = add_transaction_(db, tx, sess.get("username") or "dashboard")
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/transactions/bulk")
def create_transactions_bulk(
    payload: TransactionBulkCreate,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Create multiple transactions for a single employee/date in one call.
    """
    try:
        require_role_(sess, ["admin", "editor"])
        if not payload.items:
            raise ValueError("No items provided")
        # One base timestamp for whole batch so order is strict (sequence 0,1,2...)
        base_ts_ms = int(datetime.utcnow().timestamp() * 1000)
        results: List[Dict[str, Any]] = []
        for i, it in enumerate(payload.items):
            tx = {
                "date": payload.date,
                "empId": payload.empId,
                "type": it.type,
                "amount": it.amount,
                "site": payload.site,
                "paidBy": payload.paidBy,
                "notes": it.notes,
            }
            results.append(
                add_transaction_(
                    db, tx, sess.get("username") or "dashboard",
                    sequence=i, base_ts_ms=base_ts_ms,
                )
            )
        return {"ok": True, "data": {"count": len(results), "items": results}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/tax-invoice/state")
def get_tax_invoice_state(
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Get saved tax invoice editor state for the current workspace.
    """
    try:
        data = get_tax_invoice_state_(db)
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/tax-invoice/state")
def save_tax_invoice_state(
    payload: TaxInvoiceStatePayload,
    db: Session = Depends(get_db),
    sess: Dict[str, Any] = Depends(get_current_session),
) -> Dict[str, Any]:
    """
    Save tax invoice editor state (admin/editor).
    """
    try:
        require_role_(sess, ["admin", "editor"])
        data = save_tax_invoice_state_(
            db,
            payload.fileName,
            payload.sheetHtml,
            sess.get("username") or "dashboard",
        )
        return {"ok": True, "data": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def handle_get(
    action: str = Query("", description="Action name, similar to Apps Script doGet"),
    # Auth
    username: Optional[str] = None,
    password: Optional[str] = None,
    session: Optional[str] = None,
    # Employee params
    empId: Optional[str] = None,
    name: Optional[str] = None,
    role: Optional[str] = None,
    monthlySalary: Optional[float] = None,
    visaTotal: Optional[float] = None,
    joinDate: Optional[str] = None,
    status: Optional[str] = None,
    openingBalance: Optional[float] = None,
    # Common filters
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    month: Optional[str] = None,
    totalHours: Optional[float] = None,
    totalOvertime: Optional[float] = None,
    entryCount: Optional[int] = None,
    # Transaction params
    txId: Optional[str] = None,
    date: Optional[str] = None,
    type: Optional[str] = None,
    amount: Optional[float] = None,
    site: Optional[str] = None,
    paidBy: Optional[str] = None,
    notes: Optional[str] = None,
    id_: Optional[str] = Query(None, alias="id"),
    fileName: Optional[str] = None,
    items_b64: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Single GET endpoint that mimics the original Apps Script doGet(e) action router.
    Always returns a JSON object with { ok: bool, data?: any, error?: string }.
    """
    try:
        act = (action or "").strip()

        # Public: login
        if act == "login":
            data = login_(db, username, password)
            return {"ok": True, "data": data}

        # Public / bootstrap: create user.
        # - If there are NO users yet, allow creating the very first user without a session
        #   (so you can bootstrap an initial admin).
        # - If users already exist, require an admin session to create additional users.
        if act == "userAdd":
            username_clean = (username or "").strip()
            password_clean = (password or "").strip()
            role_clean = (role or "viewer").strip()
            if not username_clean or not password_clean:
                raise ValueError("username and password are required")
            if username_clean == SUPER_ADMIN_USERNAME:
                raise ValueError("This username is reserved")

            users_existing = db.query(User).all()
            if len(users_existing) > 0:
                # Require admin for additional users
                sess_for_user = require_session_(session)
                require_role_(sess_for_user, ["admin"])

            existing = db.query(User).filter(User.username == username_clean).first()
            if existing:
                raise ValueError(f"User already exists: {username_clean}")

            user_obj = User(username=username_clean, password=password_clean, role=role_clean or "viewer")
            db.add(user_obj)
            db.commit()
            return {"ok": True, "data": {"username": user_obj.username, "role": user_obj.role}}

        # Everything else: requires session
        sess = require_session_(session)

        if act == "ping":
            return {
                "ok": True,
                "data": {"message": "pong", "user": sess["username"], "role": sess["role"]},
            }

        # ===== Employees =====
        if act == "employees":
            return {"ok": True, "data": get_employees_(db)}

        if act == "nextEmployeeId":
            next_id = get_next_employee_id_(db)
            return {"ok": True, "data": {"nextEmpId": next_id}}

        if act == "employeeAdd":
            require_role_(sess, ["admin"])
            emp = read_employee_params_(
                empId=empId,
                name=name,
                role=role,
                monthlySalary=monthlySalary,
                visaTotal=visaTotal,
                joinDate=joinDate,
                status=status,
                openingBalance=openingBalance,
            )
            add_employee_(db, emp)
            return {"ok": True, "data": emp}

        if act == "employeeUpdate":
            require_role_(sess, ["admin"])
            emp = read_employee_params_(
                empId=empId,
                name=name,
                role=role,
                monthlySalary=monthlySalary,
                visaTotal=visaTotal,
                joinDate=joinDate,
                status=status,
                openingBalance=openingBalance,
            )
            update_employee_(db, emp)
            return {"ok": True, "data": emp}

        if act == "employeeDeactivate":
            require_role_(sess, ["admin"])
            emp_id = (empId or "").strip()
            if not emp_id:
                raise ValueError("empId required")
            data = set_employee_status_(db, emp_id, "Inactive")
            return {"ok": True, "data": data}

        if act == "employeeDelete":
            require_role_(sess, ["admin"])
            emp_id = (empId or "").strip()
            if not emp_id:
                raise ValueError("empId required")
            data = delete_employee_(db, emp_id)
            return {"ok": True, "data": data}

        # ===== Transactions =====
        if act == "transactions":
            emp_id = (empId or "").strip()
            from_s = (from_ or "").strip() or None
            to_s = (to or "").strip() or None
            data = get_transactions_(db, emp_id, from_s, to_s)
            return {"ok": True, "data": data}

        # ===== Summary =====
        if act == "summary":
            emp_id = (empId or "").strip()
            from_s = (from_ or "").strip() or None
            to_s = (to or "").strip() or None
            data = get_summary_(db, emp_id, from_s, to_s)
            return {"ok": True, "data": data}

        # ===== Time Sheet =====
        if act == "timesheetGet":
            emp_id = (empId or "").strip()
            month_s = (month or "").strip()
            data = get_timesheet_(db, emp_id, month_s)
            return {"ok": True, "data": data}

        if act == "timesheetSave":
            require_role_(sess, ["admin", "editor"])
            emp_id = (empId or "").strip()
            month_s = (month or "").strip()
            total_hours = float(totalHours or 0)
            total_overtime = float(totalOvertime or 0)
            entry_count = int(entryCount or 0)
            items_clean: Optional[List[Dict[str, Any]]] = None

            # Backward compatibility: if legacy items are sent, derive monthly totals.
            b64 = (items_b64 or "").strip()
            if b64:
                try:
                    missing_padding = len(b64) % 4
                    if missing_padding:
                        b64 += "=" * (4 - missing_padding)
                    decoded = base64.urlsafe_b64decode(b64.encode("utf-8"))
                    json_str = decoded.decode("utf-8")
                except Exception as exc:
                    raise ValueError(f"Failed to decode items_b64: {exc}") from exc
                items = json.loads(json_str)
                items_clean = sanitize_timesheet_items_(items, month_s)
                summary = summarize_timesheet_items_(items_clean)
                total_hours = float(summary["totalHours"])
                total_overtime = float(summary["totalOvertime"])
                entry_count = int(summary["entryCount"])

            data = save_timesheet_(
                db,
                emp_id,
                month_s,
                total_hours,
                total_overtime,
                entry_count,
                items_clean,
                sess.get("username") or "dashboard",
            )
            return {"ok": True, "data": data}

        if act == "timesheetDelete":
            require_role_(sess, ["admin", "editor"])
            emp_id = (empId or "").strip()
            month_s = (month or "").strip()
            data = delete_timesheet_(db, emp_id, month_s)
            return {"ok": True, "data": data}

        if act == "timesheetList":
            month_s = (month or "").strip()
            data = list_timesheets_by_month_(db, month_s)
            return {"ok": True, "data": data}

        # ===== Purchase Order Detail =====
        if act == "purchaseOrderList":
            return {"ok": True, "data": list_purchase_orders_(db)}

        if act == "purchaseOrderUpsert":
            require_role_(sess, ["admin", "editor"])
            payload_any = _decode_items_b64_json_(items_b64)
            if not isinstance(payload_any, dict):
                raise ValueError("items_b64 must contain a purchase order object")
            data = upsert_purchase_order_(db, payload_any, sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        if act == "purchaseOrderDelete":
            require_role_(sess, ["admin", "editor"])
            data = delete_purchase_order_(db, (id_ or "").strip())
            return {"ok": True, "data": data}

        if act == "purchaseOrderClear":
            require_role_(sess, ["admin", "editor"])
            data = clear_purchase_orders_(db)
            return {"ok": True, "data": data}

        if act == "plateDetailsList":
            return {"ok": True, "data": list_plate_details_(db)}

        if act == "plateDetailsReplace":
            require_role_(sess, ["admin", "editor"])
            payload_any = _decode_items_b64_json_(items_b64)
            data = replace_plate_details_(db, payload_any, sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        if act == "purchaseOrderCompaniesList":
            return {"ok": True, "data": list_purchase_order_companies_(db)}

        if act == "purchaseOrderCompanyAdd":
            require_role_(sess, ["admin", "editor"])
            data = add_purchase_order_company_(db, (name or "").strip(), sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        if act == "purchaseOrderCompaniesReplace":
            require_role_(sess, ["admin", "editor"])
            payload_any = _decode_items_b64_json_(items_b64)
            data = replace_purchase_order_companies_(db, payload_any, sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        # ===== Monthly Closing =====
        if act == "monthlyClosingList":
            return {"ok": True, "data": list_monthly_closing_entries_(db)}

        if act == "monthlyClosingUpsert":
            require_role_(sess, ["admin", "editor"])
            payload_any = _decode_items_b64_json_(items_b64)
            if not isinstance(payload_any, dict):
                raise ValueError("items_b64 must contain a monthly closing object")
            data = upsert_monthly_closing_entry_(db, payload_any, sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        if act == "monthlyClosingDelete":
            require_role_(sess, ["admin", "editor"])
            data = delete_monthly_closing_entry_(db, (id_ or "").strip())
            return {"ok": True, "data": data}

        # ===== Return =====
        if act == "returnList":
            return {"ok": True, "data": list_return_entries_(db)}

        if act == "returnUpsert":
            require_role_(sess, ["admin", "editor"])
            payload_any = _decode_items_b64_json_(items_b64)
            if not isinstance(payload_any, dict):
                raise ValueError("items_b64 must contain a return object")
            data = upsert_return_entry_(db, payload_any, sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        if act == "returnDelete":
            require_role_(sess, ["admin", "editor"])
            data = delete_return_entry_(db, (id_ or "").strip())
            return {"ok": True, "data": data}

        # ===== Tax Invoice =====
        if act == "taxInvoiceGet":
            return {"ok": True, "data": get_tax_invoice_state_(db)}

        if act == "taxInvoiceSave":
            require_role_(sess, ["admin", "editor"])
            payload_any = _decode_items_b64_json_(items_b64)
            if not isinstance(payload_any, dict):
                raise ValueError("items_b64 must contain a tax invoice state object")
            payload_name = str(payload_any.get("fileName") or fileName or "Tax Invoice").strip() or "Tax Invoice"
            payload_html = str(payload_any.get("sheetHtml") or "")
            data = save_tax_invoice_state_(db, payload_name, payload_html, sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        # Delete transaction
        if act == "deleteTransaction":
            require_role_(sess, ["admin", "editor"])
            tx_id = (txId or "").strip()
            if not tx_id:
                raise ValueError("txId required")
            data = delete_transaction_(db, tx_id)
            return {"ok": True, "data": data}

        # Add SINGLE transaction
        if act == "addTransaction":
            require_role_(sess, ["admin", "editor"])
            tx = {
                "date": (date or "").strip(),
                "empId": (empId or "").strip(),
                "type": (type or "").strip(),
                "amount": amount,
                "site": (site or "").strip(),
                "paidBy": (paidBy or "").strip(),
                "notes": (notes or "").strip(),
            }
            data = add_transaction_(db, tx, sess.get("username") or "dashboard")
            return {"ok": True, "data": data}

        # Add MULTIPLE transactions (bulk)
        if act == "addTransactionsBulk":
            require_role_(sess, ["admin", "editor"])
            emp_id = (empId or "").strip()
            date_str = (date or "").strip()
            site_str = (site or "").strip()
            paid_by_str = (paidBy or "").strip()
            b64 = (items_b64 or "").strip()

            if not emp_id:
                raise ValueError("empId required")
            if not date_str:
                raise ValueError("date required (YYYY-MM-DD)")
            if not b64:
                raise ValueError("items_b64 required")

            try:
                # Add padding if needed (frontend removes = characters)
                missing_padding = len(b64) % 4
                if missing_padding:
                    b64 += "=" * (4 - missing_padding)
                decoded = base64.urlsafe_b64decode(b64.encode("utf-8"))
                json_str = decoded.decode("utf-8")
            except Exception as exc:
                raise ValueError(f"Failed to decode items_b64: {exc}") from exc

            items = json.loads(json_str)
            if not isinstance(items, list) or len(items) == 0:
                raise ValueError("No items provided")

            # One base timestamp for whole batch; add one entry at a time (no summing)
            base_ts_ms = int(datetime.utcnow().timestamp() * 1000)
            results: List[Dict[str, Any]] = []
            for i, it in enumerate(items):
                tx = {
                    "date": date_str,
                    "empId": emp_id,
                    "type": str(it.get("type") or "").strip(),
                    "amount": float(it.get("amount") or 0),
                    "site": site_str,
                    "paidBy": paid_by_str,
                    "notes": str(it.get("notes") or "").strip(),
                }
                results.append(
                    add_transaction_(
                        db, tx, sess.get("username") or "dashboard",
                        sequence=i, base_ts_ms=base_ts_ms,
                    )
                )

            return {"ok": True, "data": {"count": len(results), "items": results}}

        return {"ok": False, "error": "Unknown action"}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# If you want to run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


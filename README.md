# Nyris — Backend V1 (paper trading)

Backend de **simulation de trading crypto** (paper trading). FastAPI + PostgreSQL + SQLAlchemy 2.0.

## Stack
- Python 3.13, FastAPI, Uvicorn
- PostgreSQL 17 (driver psycopg 3)
- SQLAlchemy 2.0 (ORM) + Alembic (migrations)
- Pydantic v2 (schémas) + pydantic-settings (config)

## Architecture
```
nyris/
├── core/      config, database, logging, exceptions
├── models/    tables SQLAlchemy (assets, simulated_trades)
├── schemas/   contrats d'API Pydantic
├── services/  logique métier (pnl pur, trades)
├── api/       routes FastAPI + dépendances
└── db/        seed de la watchlist
```
Couches : **API → services → models**. Le calcul du PnL est une fonction pure et testée.

## Configuration
Les secrets vivent **hors du dépôt**, dans `/srv/nyris/config/.env` (voir `config/.env.example`).
Variable `NYRIS_ENV_FILE` pour pointer un autre fichier en dev.

## Démarrage (sur le VPS)
```bash
cd /srv/nyris/app
source /srv/nyris/.venv/bin/activate      # ou utiliser /srv/nyris/.venv/bin/<cmd>

# 1. Migrations (création/maj du schéma)
alembic upgrade head

# 2. Seed de la watchlist (idempotent)
python -m nyris.db.seed

# 3. Lancer l'API (dev)
uvicorn nyris.main:app --host 127.0.0.1 --port 8000
```
Docs interactives : `http://127.0.0.1:8000/docs`

## Endpoints
| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | healthcheck + ping DB |
| GET | `/api/v1/assets` | actifs suivis (`?active_only=true`) |
| POST | `/api/v1/trades` | créer un trade (statut `open`) |
| GET | `/api/v1/trades` | lister (`?status=`, `limit`, `offset`) |
| GET | `/api/v1/trades/{id}` | détail |
| POST | `/api/v1/trades/{id}/close` | fermer → calcule le PnL |
| POST | `/api/v1/trades/{id}/cancel` | annuler |

## Modèle de frais (V1 = flat_rate)
Frais figés par trade, séparés entrée/sortie. PnL toujours **net de frais**.
```
entry_fee_amount = amount_invested × entry_fee_rate
net_invested     = amount_invested − entry_fee_amount
quantity         = net_invested / entry_price
exit_gross_value = quantity × exit_price
exit_fee_amount  = exit_gross_value × exit_fee_rate
exit_net_value   = exit_gross_value − exit_fee_amount
pnl_net          = exit_net_value − amount_invested
pnl_percent      = pnl_net / amount_invested × 100
```
Taux par défaut : 0.1 % à l'entrée et à la sortie. Tout est en `Decimal` (jamais `float`).

## Tests
```bash
pip install -r requirements-dev.txt
pytest -q
```

## Migrations Alembic
```bash
alembic revision --autogenerate -m "message"   # générer une migration
alembic upgrade head                            # appliquer
alembic downgrade -1                            # revenir en arrière
```

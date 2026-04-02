# Coneural MVP

AI-powered SaaS backend for organizations, departments, and document ingestion, built with FastAPI.

## Getting Started

### Prerequisites

- Python 3.10+
- MySQL server
- Redis (for background tasks)

### Clone the repository

```bash
git clone https://github.com/abhijithazra-cc/coneural_mvp.git
cd coneural_mvp
```

> **Note:** If the repository is private, you need a GitHub account with access. Use a [personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) or SSH key:
> ```bash
> git clone https://github.com/abhijithazra-cc/coneural_mvp.git
> # or with SSH:
> git clone git@github.com:abhijithazra-cc/coneural_mvp.git
> ```

### Installation

```bash
cd new_code
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Copy the example environment file and fill in your values:

```bash
cp new_code/.env.example new_code/.env
```

Edit `new_code/.env` with your database credentials, OpenAI API key, etc.

### Run the server

```bash
cd new_code
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

## Project Structure

```
new_code/
├── main.py              # FastAPI app entry point
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── app/
    ├── database.py      # SQLAlchemy setup
    ├── models/          # ORM models
    ├── routers/         # API route handlers
    ├── schemas/         # Pydantic schemas
    ├── services/        # Business logic
    ├── Rag/             # RAG pipeline (document ingestion & retrieval)
    ├── tasks/           # Background tasks
    └── utils/           # Utilities
```

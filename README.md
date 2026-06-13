# Perga API

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10-blue.svg)
![Build](https://github.com/getperga/perga-api/actions/workflows/ci.yml/badge.svg)

A personal workspace for your notes, plans, and ideas.

## Overview

**Perga API** is the core of the product.  
**[Perga Web](https://github.com/getperga/perga-web)** is a standalone **browser client** that connects to the backend to provide a user-friendly web interface.

## Screenshots

<p>
  <img src="docs/assets/api_screenshot.png" alt="Perga API" width="300" />
  <span>&nbsp;&nbsp;&nbsp;</span>
  <img src="docs/assets/planner_screenshot.png" alt="Planner" width="300" />
  <span>&nbsp;&nbsp;&nbsp;</span>
  <img src="docs/assets/notes_screenshot.png" alt="Notes" width="300" />
</p>

## Demo

You can try out Perga without installation by visiting demo version at [https://demo.getperga.me/](https://demo.getperga.me/).

## Features

- Daily planner
- Monthly and custom agendas
- Notes
- RESTful API with FastAPI
- User authentication with JWT tokens
- API Documentation with Swagger UI

## Tech Stack

- **Framework:** [FastAPI](https://fastapi.tiangolo.com/)
- **Database:** [PostgreSQL](https://www.postgresql.org/) with [SQLAlchemy](https://www.sqlalchemy.org/) ORM
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
- **Validation:** [Pydantic](https://docs.pydantic.dev/)
- **Authentication:** JWT (JSON Web Tokens)
- **Containerization:** [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL
- Docker (optional)

### Quick Start

1. Clone the repository and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure your environment by creating a `.env` file (see `.env-example`).
3. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

For detailed installation and configuration instructions, please refer to the [official documentation](https://docs.getperga.me/docs/perga-api).

## Documentation

For detailed documentation, please visit:
[https://docs.getperga.me/docs/perga-api](https://docs.getperga.me/docs/perga-api)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

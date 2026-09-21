# Perga API

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
[![CI](https://github.com/getperga/perga-api/actions/workflows/ci.yml/badge.svg)](https://github.com/getperga/perga-api/actions/workflows/ci.yml)

The backend for [Perga](https://getperga.me/) — a personal workspace for notes, plans, and ideas. The browser client lives in the [perga-web](https://github.com/getperga/perga-web) repository.

## Features

- Daily planning
- Monthly and custom agendas
- Notes management with folders, export and import
- Full-text note search
- User authentication, including Google sign-in

## Screenshots

<p>
  <img src="docs/assets/api_screenshot.png" alt="Perga API" width="300" />
  <span>&nbsp;&nbsp;&nbsp;</span>
  <img src="docs/assets/planner_screenshot.png" alt="Daily planner" width="300" />
  <span>&nbsp;&nbsp;&nbsp;</span>
  <img src="docs/assets/notes_screenshot.png" alt="Notes" width="300" />
</p>

Try the hosted demo at [demo.getperga.me](https://demo.getperga.me/).

## Tech stack

- Python 3.11 and [FastAPI](https://fastapi.tiangolo.com/)
- PostgreSQL 16 and [SQLAlchemy 2](https://www.sqlalchemy.org/)
- Docker Compose and nginx

## Documentation

Installation, configuration, and development instructions are available in the [Perga documentation](https://docs.getperga.me/docs/perga-api).

## License

Perga API is licensed under the [MIT License](LICENSE).

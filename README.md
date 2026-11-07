# Mehrgan Pakhsh Backend

Production-ready backend for **Mehrgan Pakhsh**, an online auto-parts store built with Django and Django REST Framework.

The backend provides secure authentication, catalog management, server-side cart handling, transactional checkout, inventory consistency, discounts, payments, shipments, invoices, and background processing.

## Tech Stack

- Python
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- JWT Authentication
- Docker / Docker Compose
- Nginx
- Gunicorn
- Zarinpal Payment Gateway
- OpenAPI / Swagger
- Git / GitHub

## Architecture

The project is organized into domain-focused Django applications:

```text
apps/
├── accounts/      # Authentication and users
├── catalog/       # Products, categories, brands and cars
├── cart/          # Server-side shopping cart
├── orders/        # Orders and checkout
├── discounts/     # Discounts and coupons
├── payments/      # Payment processing
├── shipments/     # Shipment tracking
├── invoices/      # Invoice domain
└── banners/       # Promotional content
```

Business-critical operations are handled on the server through dedicated service logic where appropriate.

The project follows **YAGNI, separation of concerns, explicit business rules, and purposeful abstraction**.

## Core Features

### Authentication

- Mobile-number authentication
- Secure 6-digit OTP
- OTP expiration and cooldown
- Failed-attempt protection
- JWT access and refresh tokens
- Token refresh and logout
- Guest cart → user cart merge

### Catalog

- Products
- Categories
- Brands
- Cars
- Product-to-car compatibility
- Product images
- Pricing and inventory
- Slugs
- Search and pagination

### Shopping Cart

- Guest and authenticated carts
- Add, update and remove items
- Cart clearing
- Quantity and stock validation
- Server-side subtotal and line-total calculation
- Guest cart persistence
- Guest-to-user cart merging

### Orders & Checkout

- Order creation and management
- Order items with price snapshots
- Sequential order numbers
- Order status management
- Delivery addresses and dates
- Transactional checkout
- Inventory locking with `select_for_update()`
- Atomic stock deduction
- Automatic expiration of unpaid orders

### Discounts

- Percentage and fixed discounts
- Activation periods
- Minimum order amounts
- Usage limits
- User-specific discounts
- Product, category and brand targeting
- Coupon usage tracking

### Payments

- Payment records
- Zarinpal integration
- Payment request
- Gateway callback
- Backend-authoritative payment amounts
- Payment verification and status management

### Shipments & Invoices

- Shipment management and tracking
- Shipment status synchronization
- Invoice generation and management
- Order, shipment and invoice coordination

### Background Processing

Celery and Redis handle asynchronous and scheduled operations such as automatic expiration and cancellation of unpaid orders.

```text
Celery Beat
    ↓
Expired Order Task
    ↓
Order Service
    ↓
Transactional cancellation
    ↓
Inventory restoration
```

## Data Integrity

PostgreSQL is used as the primary database with:

- UUID identifiers
- Foreign keys
- One-to-one and many-to-many relationships
- Unique constraints
- Database indexes
- Django validators
- Transactions
- Row-level locking
- Database migrations

Critical business calculations and inventory rules are enforced server-side rather than trusted from the client.

## API

The REST API is organized by domain and documented using OpenAPI.

```text
/api/accounts/
/api/catalog/
/api/banners/
/api/cart/
/api/discounts/
/api/addresses/
/api/orders/
/api/payments/
/api/shipments/
/api/invoices/
```

### API Documentation

Swagger UI:

```text
/api/docs/
```

OpenAPI schema:

```text
/api/schema/
```

The API documentation provides a clear contract for frontend integration and testing.

## Getting Started

### Prerequisites

Make sure the following tools are installed:

- Python
- Docker
- Docker Compose
- Git

PostgreSQL and Redis are provided through the Docker-based development environment.

### Installation

Clone the repository:

```bash
git clone https://github.com/HOsouli/mehrgan-store.git
cd mehrgan-store
```

Configure the required environment variables using the project's environment configuration example.

Build and start the development services:

```bash
docker compose up --build -d
```

Apply database migrations:

```bash
docker compose exec web python manage.py migrate
```

Run Django system checks:

```bash
docker compose exec web python manage.py check
```

The application is now ready for local development.

## Environment Configuration

The application uses environment-based configuration to separate application settings from deployment-specific values.

Configuration includes:

- Django secret key and debug settings
- Database connection
- Redis connection
- JWT configuration
- OTP and SMS provider credentials
- Payment gateway credentials
- Allowed hosts and trusted origins
- External service configuration

Use separate environment configurations for development and production.

**Security note:** Never commit `.env` files, API keys, passwords, private keys, or payment gateway credentials.

## Security

Security-sensitive operations are handled on the backend.

Key security considerations include:

- OTP expiration, cooldown, and failed-attempt limits
- JWT-based authentication and token rotation
- Server-side input and business-rule validation
- Backend-authoritative payment amounts
- Transactional inventory management
- Protection against duplicate payment processing
- Environment-based secret management
- HTTPS for production communication

Client-side values are not treated as authoritative for financial calculations, payment status, or inventory updates.

## Testing

Run Django system checks:

```bash
python manage.py check
```

Run the automated test suite:

```bash
python manage.py test
```

The test suite covers critical business operations, including:

- Authentication and OTP validation
- Cart operations and guest cart merging
- Order creation and inventory consistency
- Transactional checkout
- Discount validation
- Payment processing
- Order expiration and inventory restoration
- Shipment and invoice workflows

Tests involving external services should use controlled test configurations rather than real production credentials.

## Production Infrastructure

The application is deployed using Docker Compose on Ubuntu with:

```text
Internet
   ↓
Cloudflare
   ↓
Nginx
   ↓
Gunicorn / Django
   ↓
PostgreSQL
   +
Redis
   ↓
Celery Worker / Celery Beat
```

The production environment uses HTTPS, isolated service containers, PostgreSQL, Redis, Celery workers, scheduled tasks, and Nginx as the reverse proxy.

### Deployment & Operations

Useful operational commands:

Check running services:

```bash
docker compose ps
```

View application logs:

```bash
docker compose logs -f web
```

View Celery worker logs:

```bash
docker compose logs -f celery
```

Apply database migrations after deploying compatible application changes:

```bash
docker compose exec web python manage.py migrate
```

Production configuration, credentials, and server-specific files must remain separate from the public source repository.

## Verification

The implemented system has been verified through:

- Django system checks
- Authentication and JWT flows
- Guest and authenticated cart flows
- Guest cart merging
- Cart API CRUD operations
- Order creation and detail flows
- Inventory deduction and locking
- Discount validation
- Payment request flow
- Automatic order expiration
- Celery worker and scheduled task execution
- Production deployment smoke tests
- Production API testing

## Project Status

### Implemented

- Authentication and secure OTP
- JWT authentication
- Product catalog
- Server-side shopping cart
- Transactional checkout
- Inventory consistency
- Order management
- Discount and coupon system
- Zarinpal payment integration
- Shipment API
- Invoice domain
- Banner domain
- Celery and Redis
- Dockerized development and production environments
- Nginx / Gunicorn production setup
- OpenAPI / Swagger documentation
- Production deployment

### Next Steps

- Final production payment and SMS provider integration testing
- Expanded automated test coverage
- Frontend integration and end-to-end testing
- Production monitoring and observability
- Extended shipment and invoice workflows
- Torob integration

## Development Philosophy

> Keep the architecture clean, keep business rules on the server, protect data integrity, and add complexity only when the business requires it.

The goal is a maintainable backend that can evolve with the business without unnecessary technical complexity.

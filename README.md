# Mehrgan Pakhsh Backend

Production-ready backend for **Mehrgan Pakhsh**, an online auto-parts store built with Django and Django REST Framework.

The backend provides secure authentication, catalog management, server-side cart handling, transactional checkout, inventory consistency, discounts, payments, shipments, invoices, and background processing.

## Tech Stack

* Python
* Django
* Django REST Framework
* PostgreSQL
* Redis
* Celery
* JWT Authentication
* Docker / Docker Compose
* Nginx
* Gunicorn
* Zarinpal Payment Gateway
* OpenAPI / Swagger
* Git / GitHub

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

* Mobile-number authentication
* Secure 6-digit OTP
* OTP expiration and cooldown
* Failed-attempt protection
* JWT access and refresh tokens
* Token refresh and logout
* Guest cart → user cart merge

### Catalog

* Products
* Categories
* Brands
* Cars
* Product-to-car compatibility
* Product images
* Pricing and inventory
* Slugs
* Search and pagination

### Shopping Cart

* Guest and authenticated carts
* Add, update and remove items
* Cart clearing
* Quantity and stock validation
* Server-side subtotal and line-total calculation
* Guest cart persistence
* Guest-to-user cart merging

### Orders & Checkout

* Order creation and management
* Order items with price snapshots
* Sequential order numbers
* Order status management
* Delivery addresses and dates
* Transactional checkout
* Inventory locking with `select_for_update()`
* Atomic stock deduction
* Automatic expiration of unpaid orders

### Discounts

* Percentage and fixed discounts
* Activation periods
* Minimum order amounts
* Usage limits
* User-specific discounts
* Product, category and brand targeting
* Coupon usage tracking

### Payments

* Payment records
* Zarinpal integration
* Payment request
* Gateway callback
* Backend-authoritative payment amounts

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

* UUID identifiers
* Foreign keys
* One-to-one and many-to-many relationships
* Unique constraints
* Database indexes
* Django validators
* Transactions
* Row-level locking
* Database migrations

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

## Verification

The implemented system has been verified through:

* Django system checks
* Authentication and JWT flows
* Guest and authenticated cart flows
* Guest cart merging
* Cart API CRUD operations
* Order creation and detail flows
* Inventory deduction and locking
* Discount validation
* Payment request flow
* Automatic order expiration
* Celery worker and scheduled task execution
* Production deployment smoke tests
* Production API testing

## Project Status

### Implemented

* Authentication and secure OTP
* JWT authentication
* Product catalog
* Server-side shopping cart
* Transactional checkout
* Inventory consistency
* Order management
* Discount and coupon system
* Zarinpal payment integration
* Shipment API
* Invoice domain
* Banner domain
* Celery and Redis
* Dockerized development and production environments
* Nginx / Gunicorn production setup
* OpenAPI / Swagger documentation
* Production deployment

### Next Steps

* Production payment verification and hardening
* Expanded automated test coverage
* Frontend integration and end-to-end testing
* Production monitoring and observability
* Extended shipment and invoice workflows
* Torob integration

## Development Philosophy

> Keep the architecture clean, keep business rules on the server, protect data integrity, and add complexity only when the business requires it.

The goal is a maintainable backend that can evolve with the business without unnecessary technical complexity.

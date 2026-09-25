# Mehrgan Pakhsh Backend

Production-oriented backend for **Mehrgan Pakhsh**, an online auto-parts store built with Django and Django REST Framework.

The system is designed around secure authentication, transactional order processing, inventory consistency, server-side business rules, modular architecture, and maintainable REST APIs.

## Tech Stack

* Python
* Django
* Django REST Framework
* PostgreSQL
* JWT Authentication
* Celery
* Redis
* Docker / Docker Compose
* Zarinpal Payment Gateway
* OpenAPI / Swagger
* Git / GitHub

## Architecture

The backend is organized into domain-focused Django applications:

```text
apps/
├── accounts/      # Authentication and users
├── catalog/       # Products, categories, brands and cars
├── cart/          # Server-side shopping cart
├── orders/        # Orders, checkout and inventory consistency
├── discounts/     # Discount and coupon rules
├── payments/      # Payment processing
├── shipments/     # Shipment tracking
├── invoices/      # Invoice domain
└── banners/       # Promotional content
```

Business-critical workflows are separated from the HTTP layer where appropriate, with dedicated service logic for operations such as checkout and order expiration.

The project follows YAGNI, separation of concerns, explicit business rules, and minimal purposeful abstraction.

## Core Features

### Authentication and Security

* Mobile-number-based authentication
* Cryptographically secure 6-digit OTP generation
* OTP expiration
* OTP request cooldown
* Automatic invalidation of previously active OTPs
* OTP codes are never returned in API responses
* JWT access and refresh tokens
* Token refresh and logout
* Server-side input validation
* Authenticated resource ownership

Security-sensitive business rules are enforced on the backend rather than trusted from the client.

### Product Catalog

* Products
* Categories
* Brands
* Cars
* Product-to-Car compatibility
* UUID-based entity identifiers
* Product slugs
* Product pricing
* Inventory management
* Product images
* Search and filtering foundation

Product-to-Car compatibility uses a many-to-many relationship, allowing products to support multiple vehicles and keeping the catalog extensible.

### Shopping Cart

* Persistent server-side cart
* One cart per user
* Cart items
* Add, update and remove operations
* Cart clearing
* Quantity validation
* Server-side subtotal and line-total calculation

Client-provided prices and totals are not treated as authoritative.

## Order Management

The order system is the core transactional domain of the backend.

* Order creation
* Order items
* Unique sequential order numbers
* Order status management
* Delivery addresses
* Delivery date
* Order history
* Order expiration
* Discount integration
* Payment integration

### Transactional Checkout

Checkout uses:

* `transaction.atomic()`
* `select_for_update()`
* Server-side price calculation
* Server-side stock validation
* Row-level locking
* Atomic stock deduction

This protects inventory from race conditions and prevents overselling when concurrent orders target the same product.

Order-item prices are stored as snapshots, preserving the price used at the time of purchase.

### Order Expiration

Pending orders expire after 30 minutes.

Expired unpaid orders are automatically processed through Celery.

The cancellation workflow verifies the order state, checks payment status, restores reserved inventory, and cancels the order within a transactional workflow.

## Discount System

The discount domain supports:

* Percentage discounts
* Fixed-value discounts
* Activation periods
* Minimum order amounts
* Global usage limits
* Per-user usage limits
* User-specific discounts
* Product-level discounts
* Category-level discounts
* Brand-level discounts
* Order-level discounts
* Coupon usage tracking

Discount eligibility and calculation are performed entirely on the backend.

Order-level discounts are allocated across order items while preserving the final discount amount.

## Payments

Payment processing is isolated in a dedicated application.

* Payment records
* Order and payment relationship
* Payment status management
* Zarinpal integration
* Sandbox environment
* Payment request endpoint
* Gateway callback endpoint

Payment amounts are derived from trusted backend order data rather than client-provided totals.

## Background Processing

Celery and Redis are used for asynchronous and scheduled operations.

Current scheduled workflow:

```text
Celery Beat
    |
    v
Expired Order Task
    |
    v
OrderService
    |
    v
Transactional cancellation and stock restoration
```

## Database and Data Integrity

PostgreSQL is used as the primary relational database.

The data model uses:

* UUID primary keys
* Foreign keys
* One-to-one relationships
* Many-to-many relationships
* Unique constraints
* Database indexes
* Django validators
* Database migrations
* Transactional workflows
* Row-level locking

Human-friendly sequential order numbers are generated independently from UUID entity identifiers.

## API

The API is organized by domain and documented through OpenAPI.

### Authentication

```text
POST /api/accounts/auth/request-otp/
POST /api/accounts/auth/verify-otp/
POST /api/accounts/auth/refresh/
POST /api/accounts/auth/logout/
```

### Catalog

```text
GET /api/catalog/products/
GET /api/catalog/products/{slug}/
```

### Banners

```text
GET /api/banners/
```

### Cart

```text
GET    /api/cart/
POST   /api/cart/items/
PATCH  /api/cart/items/{item_id}/
DELETE /api/cart/items/{item_id}/
DELETE /api/cart/
```

### Discounts

```text
POST /api/discounts/apply/
```

### Addresses

```text
GET    /api/addresses/
POST   /api/addresses/
PATCH  /api/addresses/{id}/
DELETE /api/addresses/{id}/
```

### Orders

```text
GET  /api/orders/
POST /api/orders/
GET  /api/orders/{id}/
```

### Payments

```text
POST /api/payments/request/
GET  /api/payments/callback/
```

### Shipments

```text
GET /api/shipments/{order_id}/
```

### Invoices

```text
GET /api/invoices/{order_id}/
```

API responses use dedicated serializers for different use cases, including creation, collection, and detailed resources.

## API Documentation

Swagger UI:

```text
/api/docs/
```

OpenAPI schema:

```text
/api/schema/
```

The documented API provides a clear contract for frontend integration and API testing.

## Docker and Infrastructure

The project includes Docker-based development and service configuration.

Docker Compose is used to provide a consistent environment for the application and supporting services.

Background processing is separated from the web process through Celery workers and scheduled tasks.

## Code Quality

The backend emphasizes:

* Clean domain boundaries
* Separation of concerns
* Explicit business logic
* Reusable service-layer operations
* Strong input validation
* Backend-authoritative calculations
* Transactional consistency
* Minimal and purposeful abstractions
* Maintainable naming and structure

Complexity is introduced only when justified by actual business requirements.

## Verification

Implemented functionality has been verified through:

* Django system checks
* Database migrations
* Authentication flow testing
* JWT authentication testing
* Cart API testing
* Order creation testing
* Order detail testing
* Inventory deduction testing
* Discount validation
* Payment request testing
* Order expiration workflow

## Project Status

### Implemented

* Mobile authentication and secure OTP
* JWT authentication
* Product catalog
* Product-to-Car compatibility
* Server-side cart
* Transactional checkout
* Inventory locking and stock consistency
* Order management
* Order expiration and automatic cancellation
* Discount engine
* Coupon usage tracking
* Payment integration
* Zarinpal sandbox integration
* Shipment API foundation
* Invoice domain foundation
* Banner domain foundation
* Celery and Redis
* Docker
* PostgreSQL
* OpenAPI and Swagger
* Git and GitHub

### Roadmap

* Production payment verification and hardening
* Expanded automated test coverage
* Production deployment configuration
* Advanced API throttling
* Frontend API integration
* Torob integration
* Production monitoring and observability
* Extended shipment and invoice workflows

## Development Philosophy

> Keep the architecture clean, keep business rules on the server, protect data integrity, and add complexity only when the business requires it.

The goal is a maintainable backend that can evolve with the business without accumulating unnecessary technical complexity.

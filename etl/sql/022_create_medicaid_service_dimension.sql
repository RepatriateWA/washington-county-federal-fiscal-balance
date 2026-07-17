CREATE TABLE IF NOT EXISTS reference.medicaid_service_category (

    medicaid_service_category_id BIGSERIAL PRIMARY KEY,

    service_category_name TEXT NOT NULL UNIQUE,

    is_adjustment BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
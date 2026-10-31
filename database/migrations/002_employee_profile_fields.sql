-- 002_employee_profile_fields.sql
-- Adds the minimum database fields required by the employee/admin
-- personal-information and contact-details UI. Safe to apply once
-- after 001_initial_database_migration.sql.
ALTER TABLE employees
    ADD COLUMN date_of_birth DATE NULL,
    ADD COLUMN gender VARCHAR(30) NULL,
    ADD COLUMN blood_group VARCHAR(10) NULL,
    ADD COLUMN father_name VARCHAR(100) NULL,
    ADD COLUMN marital_status VARCHAR(30) NULL,
    ADD COLUMN nationality VARCHAR(60) NULL,
    ADD COLUMN language VARCHAR(100) NULL,
    ADD COLUMN alternate_phone VARCHAR(20) NULL,
    ADD COLUMN address VARCHAR(255) NULL,
    ADD COLUMN city VARCHAR(80) NULL,
    ADD COLUMN state VARCHAR(60) NULL,
    ADD COLUMN pin_code VARCHAR(10) NULL;

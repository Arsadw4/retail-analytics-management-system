-- 003_user_profile_fields.sql
-- Gives every authenticated user (including administrators who do not have
-- an employees HR row) a persistent personal/contact/quick-info profile.
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INT PRIMARY KEY,
    date_of_birth DATE NULL,
    gender VARCHAR(30) NULL,
    blood_group VARCHAR(10) NULL,
    father_name VARCHAR(100) NULL,
    marital_status VARCHAR(30) NULL,
    nationality VARCHAR(60) NULL,
    language VARCHAR(100) NULL,
    phone VARCHAR(20) NULL,
    designation VARCHAR(100) NULL,
    alternate_phone VARCHAR(20) NULL,
    address VARCHAR(255) NULL,
    city VARCHAR(80) NULL,
    state VARCHAR(60) NULL,
    pin_code VARCHAR(10) NULL,
    department_id INT NULL,
    designation_id INT NULL,
    date_of_joining DATE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_profiles_user
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_profiles_department
        FOREIGN KEY (department_id) REFERENCES departments(department_id) ON DELETE SET NULL,
    CONSTRAINT fk_user_profiles_designation
        FOREIGN KEY (designation_id) REFERENCES designations(designation_id) ON DELETE SET NULL,
    INDEX idx_user_profiles_department (department_id),
    INDEX idx_user_profiles_designation (designation_id)
);

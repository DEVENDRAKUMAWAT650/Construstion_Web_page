CREATE DATABASE IF NOT EXISTS construction_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE construction_db;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(190) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'customer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    building_type VARCHAR(100) NOT NULL DEFAULT 'Residential Villa',
    location VARCHAR(255) DEFAULT '',
    stage VARCHAR(100) NOT NULL DEFAULT 'Planning & Foundation',
    progress INT NOT NULL DEFAULT 15,
    start_date VARCHAR(50) DEFAULT '',
    expected_completion VARCHAR(50) DEFAULT '',
    total_area VARCHAR(100) DEFAULT '',
    supervisor_name VARCHAR(120) DEFAULT '',
    supervisor_phone VARCHAR(30) DEFAULT '',
    image_url LONGTEXT DEFAULT NULL,
    latest_update TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_cp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS customer_project_photos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    image_url LONGTEXT NOT NULL,
    caption VARCHAR(255) DEFAULT '',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cpp_project FOREIGN KEY (project_id) REFERENCES customer_projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    category VARCHAR(80) NOT NULL,
    description TEXT NOT NULL,
    image_url LONGTEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS enquiries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(190) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    project_type VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO projects (title, category, description, image_url)
SELECT 'Residential Villa', 'Residential', 'Contemporary family home in Jaipur, Rajasthan.',
'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&q=80'
WHERE NOT EXISTS (SELECT 1 FROM projects WHERE title='Residential Villa');
INSERT INTO projects (title, category, description, image_url)
SELECT 'Commercial Complex', 'Commercial', 'Modern commercial space for offices and retail.',
'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80'
WHERE NOT EXISTS (SELECT 1 FROM projects WHERE title='Commercial Complex');
INSERT INTO projects (title, category, description, image_url)
SELECT 'Office Building', 'Commercial', 'Contemporary office building concept.',
'https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1200&q=80'
WHERE NOT EXISTS (SELECT 1 FROM projects WHERE title='Office Building');
INSERT INTO projects (title, category, description, image_url)
SELECT 'Infrastructure Project', 'Infrastructure', 'Infrastructure and civil engineering project concept.',
'https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=1200&q=80'
WHERE NOT EXISTS (SELECT 1 FROM projects WHERE title='Infrastructure Project');
INSERT INTO projects (title, category, description, image_url)
SELECT 'Renovation Project', 'Renovation', 'Interior renovation with modern finishes.',
'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1200&q=80'
WHERE NOT EXISTS (SELECT 1 FROM projects WHERE title='Renovation Project');
INSERT INTO projects (title, category, description, image_url)
SELECT 'Industrial Building', 'Industrial', 'Functional industrial building concept.',
'https://images.unsplash.com/photo-1565008447742-97f6f38c985c?auto=format&fit=crop&w=1200&q=80'
WHERE NOT EXISTS (SELECT 1 FROM projects WHERE title='Industrial Building');

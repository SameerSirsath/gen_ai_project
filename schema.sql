CREATE DATABASE IF NOT EXISTS ai_sdr_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai_sdr_db;

-- 1. Company Profile (The User's Company)
CREATE TABLE IF NOT EXISTS companies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(150),
    value_proposition TEXT,
    services_offered TEXT,
    case_studies TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 2. Leads (Target Clients)
CREATE TABLE IF NOT EXISTS leads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    contact_name VARCHAR(150),
    email VARCHAR(255) UNIQUE,
    website_url VARCHAR(500),
    status ENUM('Pending', 'Processing', 'Drafted', 'Sent', 'Failed') DEFAULT 'Pending',
    mode ENUM('Auto', 'Manual') DEFAULT 'Manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Lead Context (Raw Information & NLP Sync Status)
CREATE TABLE IF NOT EXISTS lead_context (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lead_id INT NOT NULL,
    raw_text LONGTEXT NOT NULL,
    nlp_processed BOOLEAN DEFAULT FALSE,
    vector_synced BOOLEAN DEFAULT FALSE,
    source_type VARCHAR(50) DEFAULT 'Manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

-- 4. Email Logs (Generated & Sent Emails)
CREATE TABLE IF NOT EXISTS email_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lead_id INT NOT NULL,
    subject VARCHAR(500),
    body LONGTEXT,
    evaluator_score VARCHAR(50),
    evaluator_reasoning TEXT,
    sent_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

-- 5. API Keys (Encrypted at Rest)
CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(100) NOT NULL,       -- e.g., 'groq', 'gemini'
    key_alias VARCHAR(150) NOT NULL,      -- e.g., 'Contributor 1 - Key A'
    key_value LONGTEXT NOT NULL,          -- Fernet ciphertext
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

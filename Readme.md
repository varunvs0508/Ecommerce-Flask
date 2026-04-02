# 🛍️ CopVizz - E-commerce Web Application
Built as part of hands-on learning in full-stack development and cloud deployment.

![Flask](https://img.shields.io/badge/Backend-Flask-blue)
![MySQL](https://img.shields.io/badge/Database-MySQL-orange)
![AWS](https://img.shields.io/badge/Deployment-AWS%20EC2-yellow)
![Nginx](https://img.shields.io/badge/Web%20Server-Nginx-green) 
![Gunicorn](https://img.shields.io/badge/WSGI-Gunicorn-red)

A production-ready **full-stack E-commerce Web Application** built using **Flask, MySQL, and AWS EC2**, deployed with **Nginx + Gunicorn**.

---

## 📌 Overview

**CopVizz** is a scalable Flask-based e-commerce platform where users can browse products, register accounts, and interact with a dynamic shopping experience. Designed with a production-ready architecture following industry deployment practices.

✔ Deployed on AWS EC2

✔ Nginx as reverse proxy

✔ Gunicorn for production WSGI handling

---

## 🚀 Live Demo

👉 http://3.111.29.84

⚠️ Hosted on AWS EC2 (may take a few seconds to load if instance is idle)

---

## 🧰 Tech Stack

| Layer           | Technology           |
| --------------- | -------------------- |
| Backend         | Flask (Python)       |
| Frontend        | HTML, CSS, Bootstrap |
| Database        | MySQL                |
| Server          | AWS EC2 (Ubuntu)     |
| Web Server      | Nginx                |
| WSGI Server     | Gunicorn             |
| Version Control | Git & GitHub         |

---

## ✨ Features

### 👤 Authentication

* User registration & login
* Secure session handling

### 🛍️ Shopping

* Browse product categories
* Product image display
* Responsive UI

### ❤️ Additional

* Wishlist UI
* Cart interface
* Clean user experience

---

## ⚙️ Local Setup

```bash
# Clone repository
git clone https://github.com/varunvs0508/Ecommerce-Flask.git

# Navigate into project
cd Ecommerce-Flask

# Create virtual environment
python -m venv venv

# Activate environment
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate          # Windows

# Install dependencies
pip install -r requirements.txt

# Run application
python app.py
```

---

## 🌐 AWS Deployment

### 🔹 Install Dependencies

```bash
sudo apt update
sudo apt install python3-pip python3-venv nginx mysql-server -y
```

---

### 🔹 Run Gunicorn

```bash
/home/ubuntu/Ecommerce-Flask/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

---

### 🔹 Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/default
```

```nginx
server {
    listen 80;
    server_name 3.111.29.84;

    location / {
        proxy_pass http://127.0.0.1:8000;
    }

    location /static {
        alias /home/ubuntu/Ecommerce-Flask/static;
    }
}
```

---

### 🔹 Enable & Start Service

```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl start ecommerce
sudo systemctl enable ecommerce
```

---

## 🔄 Deployment Script

```bash
./deploy.sh
```

✔ Pull latest code from GitHub  
✔ Install/update dependencies  
✔ Restart Gunicorn service  

---

## ☁️ AWS Architecture

```
Client (Browser) → Nginx → Gunicorn → Flask Application → MySQL Database
```

### Flow Explanation
- Nginx handles incoming requests and static files
- Gunicorn runs the Flask app
- Flask processes logic and interacts with MySQL

---

## 🔐 Environment Variables (.env)

Create a `.env` file in the root directory:

```env
SECRET_KEY=your_secret_key
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=ecommerce
```

---

## 📁 Project Structure

```
Ecommerce-Flask/
│
├── app.py
├── config.py
├── models/
├── routes/
├── templates/
├── static/
├── venv/
├── requirements.txt
└── deploy.sh
```

---

## ⚠️ Notes

* Linux is case-sensitive (especially for static files)
* Never commit `.env` file to GitHub
* Use swap memory for low RAM EC2 instances
* Use `systemctl status ecommerce` for debugging
* Check logs using: `journalctl -u ecommerce -f`

---

## 📬 Connect With Me

<p align="center">
  <a href="https://www.linkedin.com/in/varun-sai-kedarisetty-bb86bb23b/" target="_blank">
    <img src="https://img.shields.io/badge/LinkedIn-Visit%20Profile-blue?style=for-the-badge&logo=linkedin" />
  </a>
</p>

---
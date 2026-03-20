# 📦 ML CI/CD Pipeline — VSCode'dan GitHub'a Push Talimatı

## 📁 Proje Yapısı

```
ml-cicd-project/
├── .github/
│   └── workflows/
│       └── ml-pipeline.yml      ← GitHub Actions pipeline (4 stage)
├── docker/
│   └── Dockerfile               ← ML model container
├── scripts/
│   ├── deploy_sagemaker.py      ← SageMaker endpoint deploy
│   └── trigger_pipeline.py      ← SageMaker pipeline trigger + lineage
├── src/                         ← ML model kaynak kodun buraya gelir
├── tests/                       ← Unit testlerin buraya gelir
├── requirements.txt
└── .gitignore
```

---

## 🔐 Adım 1 — GitHub Secrets Ayarla

GitHub reponuza gidin → **Settings → Secrets and variables → Actions**

Şu secret'ları ekleyin:

| Secret Adı              | Değer                              |
|-------------------------|------------------------------------|
| `AWS_ACCESS_KEY_ID`     | AWS IAM kullanıcı access key       |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM kullanıcı secret key       |
| `SAGEMAKER_ROLE_ARN`    | SageMaker execution role ARN       |

---

## 💻 Adım 2 — VSCode'da Projeyi Aç

```bash
# Terminal'de proje klasörüne gir
cd ml-cicd-project

# Git başlat
git init

# VSCode ile aç
code .
```

---

## 🔗 Adım 3 — GitHub'a Bağla

GitHub'da yeni bir repo oluşturun (örn: `ml-cicd-project`)

```bash
git remote add origin https://github.com/KULLANICI_ADIN/ml-cicd-project.git
```

---

## 📤 Adım 4 — İlk Push

```bash
# Tüm dosyaları stage'e al
git add .

# Commit yap
git commit -m "feat: initial ML CI/CD pipeline setup"

# main branch oluştur ve push et
git branch -M main
git push -u origin main
```

---

## ⚙️ Pipeline Nasıl Çalışır?

```
Push to main
    │
    ▼
[Stage 1] 🔍 Lint & Test
    │  flake8, black, isort, pytest + coverage
    │
    ▼
[Stage 2] 🐳 Docker Build & Push
    │  ECR'a image push edilir
    │
    ▼
[Stage 3] 🚀 Deploy to AWS
    │  SageMaker endpoint güncellenir/oluşturulur
    │
    ▼
[Stage 4] ⚙️ Trigger SageMaker Pipeline
       Model eğitim pipeline'ı başlatılır
       Lineage SSM'e kaydedilir
```

- **develop** branch'e push → sadece Stage 1 çalışır (lint & test)
- **main** branch'e push → 4 stage'in tamamı çalışır
- **Pull Request** açıldığında → sadece Stage 1 çalışır

---

## 🔍 Pipeline Takibi

GitHub reponuzda:
- **Actions** sekmesine tıklayın
- Her commit için pipeline durumunu görebilirsiniz
- Herhangi bir stage'e tıklayarak detaylı log görüntüleyebilirsiniz

---

## ✅ Article'daki Prensiplerle Bağlantı

| Article Prensibi          | Pipeline Karşılığı                        |
|---------------------------|-------------------------------------------|
| Repeatability             | Her push aynı 4 stage'i çalıştırır       |
| Scalability               | SageMaker endpoint otomatik deploy        |
| Transparency/Lineage      | SSM'e commit SHA + execution ARN kaydı   |
| Error handling            | Her stage fail olursa sonraki çalışmaz   |
| Monitoring                | Coverage report + GitHub Actions logs    |

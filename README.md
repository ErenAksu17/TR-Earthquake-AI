# TR Earthquake AI

**TR Earthquake AI**, Türkiye'deki depremleri analiz eden ve görselleştiren; ayrıca yapay zeka destekli risk değerlendirmesi yapmaya yönelik bir veri analizi uygulamasıdır.

## Özellikler

- Deprem verilerini harita üzerinde görselleştirme  
- Tarih, büyüklük, derinlik gibi filtrelerle detaylı analiz  
- Yıllık ve aylık deprem frekansı grafikleri  
- Diri fay hatlarının gösterimi ve risk skorlarına göre analiz  
- Yapay zeka ile ön tahmin denemeleri  
- Veri setini CSV olarak indirme imkânı  

## Veri Kaynağı

- **AFAD** (resmî olarak yayımlanmış geçmiş deprem verileri)

## Kurulum

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Uygulamayı Başlat

```bash
streamlit run app/dashboard.py
```

## Not

Bu proje akademik veya bilimsel bir doğruluk iddiası taşımaz. Tamamen geliştirme, analiz ve veri görselleştirme amaçlıdır. Risk skorları deneysel olarak hesaplanmıştır.
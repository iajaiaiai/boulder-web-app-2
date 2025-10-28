# Boulder Web App v2

A comprehensive property analysis tool for Boulder County that automatically downloads property documents, performs OCR, and generates professional Title Examiner's Reports using AI.

## 🚀 Features

- **Automated PDF Download**: Downloads property documents from Boulder County portal
- **Advanced OCR**: Multi-method OCR with intelligent fallback selection
- **AI-Powered Analysis**: LLM with context-aware error correction for OCR mistakes
- **Professional Reports**: Clean, structured Title Examiner's Reports with bold headers
- **Session Persistence**: Maintains authentication state across runs
- **Headless Operation**: Production-ready with invisible browser automation

## 🛠️ Technology Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React (JavaScript)
- **Browser Automation**: Playwright
- **OCR**: OCRmyPDF, Tesseract, PyMuPDF
- **AI**: Hugging Face API (GPT-OSS-20B)
- **Session Management**: Persistent browser state

## 📋 Prerequisites

- Python 3.12+
- Node.js (for frontend)
- Chrome browser (system Chrome preferred)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables (Optional)

The app works out of the box with a default API key. For production or to use your own API key:

```bash
export HUGGINGFACE_API_KEY=your_api_key_here
```

Or create a `.env` file:
```bash
cp .env.example .env
# Edit .env with your API key
```

### 3. Start Backend

```bash
python3 app_v2_clean.py
```

### 4. Start Frontend

```bash
python3 -m http.server 3000 --bind 127.0.0.1
```

### 5. Access Application

Open http://localhost:3000 in your browser

## 🔧 Configuration

### Browser Settings

The app uses headless mode by default. To enable visible browser for debugging:

```python
downloader = BoulderPortalDownloader(limit=limit, headless=False)
```

## 📊 OCR Quality

The app uses a multi-method approach for optimal OCR quality:

1. **OCRmyPDF Optimized**: Best for scanned PDFs
2. **Tesseract High-Res**: Direct image processing with enhancement
3. **PyMuPDF Fallback**: For text-based PDFs

The system automatically selects the best result based on text quality scoring.

## 🤖 AI Analysis

The LLM performs intelligent error correction:
- Fixes common OCR mistakes (e.g., "amsurit" → "amount")
- Provides context-aware analysis
- Generates professional, structured reports

## 📁 File Structure

```
boulder-web-app-2/
├── app_v2_clean.py              # Main FastAPI backend
├── boulder_downloader_clean.py  # PDF downloader with Playwright
├── improved_ocr_extractor.py    # Multi-method OCR processor
├── app.js                       # React frontend
├── index.html                   # Frontend HTML
├── package.json                 # Frontend dependencies
├── requirements.txt             # Backend dependencies
├── boulder_storage_state.json   # Session persistence
├── .env.example                 # Environment variables template
└── README.md                    # This file
```

## 🔐 Session Management

The app maintains authentication state in `boulder_storage_state.json`. This file:
- Preserves login sessions across restarts
- Enables headless operation
- Reduces authentication overhead

## 🌐 Deployment

### Local Development
- Backend: http://localhost:8001
- Frontend: http://localhost:3000

### Cloud Deployment
- Update `BACKEND_URL` in `app.js` for production
- Ensure all dependencies are installed
- Set environment variables in your deployment platform

## 📝 Usage

1. Enter a property query (e.g., "TR NBR 910 WALKER RANCH AREA")
2. Set document limit (default: 1)
3. Click "Analyze Property"
4. Wait for analysis to complete
5. Review the professional Title Examiner's Report

## 🔍 Report Sections

- **Property Identification**: Parcel number, address, legal description
- **Current Ownership**: Owner details and ownership type
- **Chain of Title**: Ownership history
- **Liens and Encumbrances**: Financial claims and liens
- **Easements & Rights-of-Way**: Access rights and restrictions
- **Covenants, Conditions & Restrictions**: CC&Rs and HOA rules
- **Taxes & Assessments**: Tax status and assessments
- **Exceptions & Observations**: Issues requiring attention
- **Summary Opinion**: Professional recommendations

## 🐛 Troubleshooting

### OCR Issues
- Ensure `ocrmypdf` is properly installed
- Check Tesseract installation
- Verify PDF file accessibility

### Browser Issues
- Install Chrome browser
- Check Playwright browser installation
- Verify session state file permissions

### API Issues
- Verify Hugging Face API key in environment variables
- Check internet connectivity
- Review API rate limits

## 📄 License

MIT License

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📞 Support

For issues or questions, please create an issue in the GitHub repository.
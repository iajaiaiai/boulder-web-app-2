#!/usr/bin/env python3
"""
Boulder Property Analyzer - FastAPI Backend
Comprehensive property analysis using OCR and LLM
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import the downloader and OCR modules
from boulder_downloader_clean import BoulderPortalDownloader
from improved_ocr_extractor import improved_ocr_process

app = FastAPI(title="Boulder Property Analyzer API", version="1.0.0")
@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/healthz")
def healthz():
    return {"ok": True}

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage (in production, use a database)
jobs: Dict[str, Dict] = {}

class AnalysisRequest(BaseModel):
    query: str
    limit: Optional[int] = 1

class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    message: str

def save_jobs():
    """Save jobs to disk for persistence"""
    with open("jobs.json", "w") as f:
        json.dump(jobs, f, indent=2)

def load_jobs():
    """Load jobs from disk"""
    global jobs
    if os.path.exists("jobs.json"):
        with open("jobs.json", "r") as f:
            jobs = json.load(f)

def update_progress(job_id: str, progress: int, message: str):
    """Update job progress"""
    if job_id in jobs:
        jobs[job_id]["progress"] = progress
        jobs[job_id]["message"] = message
        save_jobs()

@app.on_event("startup")
async def startup_event():
    """Load existing jobs on startup"""
    load_jobs()

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_property(request: AnalysisRequest):
    """Start property analysis"""
    job_id = str(uuid.uuid4())
    
    jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "progress": 0,
        "message": "Analysis started",
        "query": request.query,
        "limit": request.limit,
        "created_at": datetime.now().isoformat(),
        "results": None
    }
    
    save_jobs()
    
    # Start analysis in background
    asyncio.create_task(run_analysis_async(job_id, request.query, request.limit))
    
    return AnalysisResponse(
        job_id=job_id,
        status="processing",
        message="Analysis started"
    )

@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and results"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id]

@app.get("/job/{job_id}/pdfs")
async def get_job_pdfs(job_id: str):
    """Get PDFs for a specific job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    # If job has session-specific PDFs, use those
    if "session_pdfs" in job and "pdf_directory" in job:
        pdf_dir = Path(job["pdf_directory"])
        pdfs = []
        for filename in job["session_pdfs"]:
            pdf_file = pdf_dir / filename
            if pdf_file.exists():
                pdfs.append({
                    "filename": filename,
                    "size": pdf_file.stat().st_size,
                    "created": pdf_file.stat().st_mtime
                })
        print(f"📄 Returning {len(pdfs)} session-specific PDFs for job {job_id}")
        return {"pdfs": pdfs}
    
    # NO FALLBACK - Only return session-specific PDFs
    return {"pdfs": []}

async def run_analysis_async(job_id: str, query: str, limit: int = 1):
    """Run the complete analysis workflow"""
    try:
        print(f"🚀 Starting analysis job {job_id} for query: '{query}'")
        
        # Step 1: Download PDFs
        update_progress(job_id, 10, "🔍 Initializing analysis...")
        update_progress(job_id, 20, "📥 Downloading documents...")
        
        print(f"📥 Running downloader for: {query}")
        # Use a session-scoped download directory to avoid cross-session contamination
        session_download_dir = f"session_{job_id}_pdfs"
        downloader = BoulderPortalDownloader(limit=limit, headless=True, download_dir=session_download_dir)
        
        # Run downloader
        loop = asyncio.get_event_loop()
        download_result = await downloader.download_all_pdfs(query)
        
        if not download_result or download_result['count'] == 0:
            print("❌ No PDFs were downloaded")
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "No PDFs were downloaded"
            save_jobs()
            return
        
        download_count = download_result['count']
        downloaded_filenames = download_result['files']
        
        print(f"✅ Download completed: {download_count} files downloaded")
        print(f"📄 Downloaded files: {downloaded_filenames}")
        update_progress(job_id, 40, f"📥 Downloaded {download_count} documents successfully")
        
        # Get the actual downloaded files from the download directory
        pdf_dir = Path(downloader.download_dir)
        downloaded_pdfs = [pdf_dir / filename for filename in downloaded_filenames]
        
        print(f"📁 Using {len(downloaded_pdfs)} specific PDFs for this session:")
        for pdf in downloaded_pdfs:
            print(f"  - {pdf.name}")
        
        # Store session-specific PDF information IMMEDIATELY after download
        jobs[job_id]["pdf_directory"] = str(pdf_dir)
        jobs[job_id]["session_pdfs"] = downloaded_filenames
        save_jobs()  # Save immediately so it's available for analysis
        
        # Step 2: Process PDFs with OCR
        update_progress(job_id, 50, "🔍 Processing documents with OCR...")
        
        # ALWAYS use session-specific PDFs - NO global directory fallback
        pdf_files_to_process = []
        
        if "session_pdfs" in jobs[job_id] and "pdf_directory" in jobs[job_id]:
            # Use session-specific PDFs
            pdf_dir = Path(jobs[job_id]["pdf_directory"])
            session_pdf_names = jobs[job_id]["session_pdfs"]
            
            print(f"📁 Using session-specific PDFs from: {pdf_dir}")
            for pdf_name in session_pdf_names:
                pdf_file = pdf_dir / pdf_name
                if pdf_file.exists():
                    pdf_files_to_process.append(pdf_file)
                    print(f"📄 Found session PDF: {pdf_name}")
                else:
                    print(f"⚠️  Session PDF not found: {pdf_name}")
        else:
            # NO FALLBACK - This should never happen if download worked correctly
            print("❌ ERROR: No session-specific PDFs found!")
            print("❌ This indicates a bug in the download process")
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "No session-specific PDFs found - download may have failed"
            save_jobs()
            return

        if not pdf_files_to_process:
            print("⚠️  No PDF files to process")
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "No PDF files to process"
            save_jobs()
            return

        print(f"📄 Processing {len(pdf_files_to_process)} PDF files")
        update_progress(job_id, 60, f"🔍 Processing {len(pdf_files_to_process)} documents...")
        
        # Step 3: Extract text from PDFs - ONLY process session-specific PDFs
        update_progress(job_id, 70, "📝 Extracting text from documents...")
        
        # Create a temporary directory with only session PDFs
        session_dir = Path(f"session_{job_id}")
        session_dir.mkdir(exist_ok=True)
        
        # Copy session PDFs to session directory
        for pdf_file in pdf_files_to_process:
            dest_file = session_dir / pdf_file.name
            shutil.copy2(pdf_file, dest_file)
            print(f"📋 Copied {pdf_file.name} to session directory")
        
        # Run OCR on session PDFs
        print(f"🔍 Running improved OCR process on {session_dir}")
        loop = asyncio.get_event_loop()
        combined_text_file = await loop.run_in_executor(None, improved_ocr_process, str(session_dir))
        
        if not combined_text_file or not Path(combined_text_file).exists():
            print("❌ OCR processing failed")
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "OCR processing failed"
            save_jobs()
            return
        
        print(f"✅ Improved OCR completed successfully")
        update_progress(job_id, 80, "📝 Text extraction completed")
        
        # Step 4: LLM Analysis
        update_progress(job_id, 90, "🤖 Analyzing with AI...")
        
        print(f"📄 Using combined OCR text file: {combined_text_file}")
        
        # Load OCR results
        with open(combined_text_file, 'r') as f:
            text_data = json.load(f)
        
        # Extract text from the improved OCR structure
        combined_text = ""
        document_info = []
        if 'ocr_texts' in text_data:
            # Extract all text from all OCR'd files
            ocr_texts = text_data['ocr_texts']
            all_texts = []
            doc_num = 1
            for filename, file_data in ocr_texts.items():
                if 'extracted_text' in file_data:
                    # Add document separator with filename
                    all_texts.append(f"\n{'='*80}\nDOCUMENT {doc_num}: {filename}\n{'='*80}\n")
                    all_texts.append(file_data['extracted_text'])
                    document_info.append(f"Document {doc_num}: {filename}")
                    doc_num += 1
            combined_text = '\n\n'.join(all_texts)
        elif 'extracted_texts' in text_data:
            # Fallback to old format
            extracted_texts = text_data['extracted_texts']
            all_texts = []
            for filename, file_data in extracted_texts.items():
                if 'extracted_text' in file_data:
                    all_texts.append(file_data['extracted_text'])
            combined_text = '\n\n'.join(all_texts)
        
        if not combined_text.strip():
            print("❌ No text content found in combined text file")
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "No text content could be extracted from PDFs"
            save_jobs()
            return
        
        print(f"📄 Extracted {len(combined_text)} characters of text")
        
        # REMOVED GARBLED TEXT CHECK - Always use LLM for better analysis
        # Try LLM analysis first, fallback to basic analysis
        try:
            print("🤖 Starting LLM analysis...")
            # Use Hugging Face API for analysis
            HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "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")
            MODEL = "openai/gpt-oss-20b:together"
            
            print(f"📊 Text length for LLM: {len(combined_text)} characters")
            
            # Build document list for the prompt
            docs_list = '\n'.join(document_info) if document_info else "Multiple documents"
            
            prompt = f"""Create a professional Title Examiner's Report based on the following document text. Use context clues to correct obvious OCR errors (e.g., "amsurit" should be "amount", "Scoerads" should be "State of").

DOCUMENT TEXT TO ANALYZE:
{combined_text[:8000]}

Format your response as a clean, professional report without visible markdown formatting. Use proper spacing, indentation, and structure for optimal human readability.

**TITLE EXAMINER'S REPORT**

**PROPERTY IDENTIFICATION**
Parcel Number (APN or PID): 
Subdivision / Plat: 
Legal Description: 
Property Address: 
Recording Information: 
County / Jurisdiction: 
Land Use / Zoning: 

**LEGAL DESCRIPTION ANALYSIS**
Provide the legal description found in the document and note any inconsistencies or issues.

**CURRENT OWNERSHIP**
Owner(s) of Record: 
Ownership Type: 
Grantor(s): 
Deed Type: 
Date of Transfer: 
Source Document(s): 

**CHAIN OF TITLE**
List prior transfers or ownership changes mentioned in the document. If none found, state "No prior transfers identified."

**LIENS AND ENCUMBRANCES**
Mortgage or Deed of Trust: 
Lienholders or Secured Parties: 
Judgment or Tax Liens: 
UCC Filings: 
Release or Satisfaction Documents: 

**EASEMENTS & RIGHTS-OF-WAY**
Beneficiary: 
Burdened Property: 
Purpose: 
Recorded Location: 
Duration / Conditions: 
If none found, state "No easements identified."

**COVENANTS, CONDITIONS & RESTRICTIONS**
List any CC&Rs, declarations, HOA rules, or use limitations. If none found, state "No CC&Rs identified."

**TAXES & ASSESSMENTS**
Assessor's Parcel Number: 
Current Assessed Owner: 
Tax Status: 
Special Assessments: 

**EXCEPTIONS & OBSERVATIONS**
List any exceptions to title or relevant observations:
• Gaps or inconsistencies in ownership chain
• Missing releases or partial reconveyances  
• Ambiguous legal descriptions
• Potential survey or boundary issues
• Any red flags requiring follow-up research

**SUMMARY OPINION**
Current Owner: 
Title Status: 
Key Issues: 
Recommendations: 

IMPORTANT INSTRUCTIONS:
1. Use context clues to correct obvious OCR errors (e.g., "amsurit" = "amount", "Scoerads" = "State of")
2. Format for clean human reading - no visible markdown symbols
3. Use proper spacing and indentation
4. If information is not found, state "Not Available" rather than guessing
5. Extract specific information from the text provided"""
            
            # Call Hugging Face API via router
            from openai import OpenAI
            
            print("🔧 Creating OpenAI client...")
            client = OpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=HF_API_KEY,
            )
            print("✅ OpenAI client created successfully")
            
            print("🤖 Calling Hugging Face API for analysis...")
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10000,
                temperature=0.1
            )
            print("✅ API call completed successfully")
            
            llm_analysis = response.choices[0].message.content
            print(f"📊 LLM response length: {len(llm_analysis)} characters")
            
            # Clean up formatting for better readability
            if llm_analysis:
                # Keep bold markdown (**text**) for section headings as it's professional
                # Only remove double underscores which are not commonly used
                llm_analysis = llm_analysis.replace('__', '')
                # Clean up multiple spaces (but keep newlines for structure)
                llm_analysis = re.sub(r'[ \t]+', ' ', llm_analysis)
                # Remove leading/trailing whitespace from each line
                llm_analysis = '\n'.join(line.strip() for line in llm_analysis.split('\n'))
                llm_analysis = llm_analysis.strip()
            
            # Validate LLM response
            if not llm_analysis or len(llm_analysis.strip()) == 0:
                print("⚠️ LLM returned empty response, falling back to basic analysis")
                llm_analysis = create_basic_analysis(combined_text)
            else:
                print("✅ LLM analysis completed successfully")
                
        except Exception as e:
            print(f"⚠️  LLM analysis failed: {str(e)}")
            print("🔄 Falling back to basic analysis...")
            llm_analysis = create_basic_analysis(combined_text)
        
        # Store results
        jobs[job_id]["results"] = {
            "results": [{
                "llm_analysis": llm_analysis,
                "document_count": len(pdf_files_to_process),
                "text_length": len(combined_text)
            }]
        }
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = "✅ Analysis completed successfully!"
        save_jobs()
        
        print(f"✅ Job {job_id} completed successfully")
        
    except Exception as e:
        print(f"❌ Job {job_id} failed: {str(e)}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Analysis failed: {str(e)}"
        jobs[job_id]["progress"] = 0
        save_jobs()

def create_basic_analysis(text: str) -> str:
    """Create a basic analysis when LLM fails"""
    return f"""**Basic Property Analysis**

**Document Summary:**
- Text extracted: {len(text)} characters
- Analysis method: Basic text processing

**Key Information Found:**
{text[:1000]}...

**Note:** This is a basic analysis. For detailed title examination, please retry the analysis.
"""

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)

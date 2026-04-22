"""
Document Retriever Agent

Retrieves SEC filing context from ChromaDB to enrich downstream agents.
Fetches filings from EDGAR if not cached, chunks and stores them,
then queries for relevant context.
"""

import time
import os
from typing import Dict, Any
from schemas.state import ResearchState


def document_retriever_agent(state: ResearchState) -> ResearchState:
    """
    Document Retriever Agent — fetches and queries SEC filings for context.

    Populates state["sec_filing_context"] with:
    - risk_factors_context: Relevant risk factor excerpts
    - mda_context: Relevant MD&A excerpts
    - filing_date: Date of the most recent filing used
    - source_url: URL of the filing
    - available: Boolean indicating if filing context is available

    Args:
        state: Current research state

    Returns:
        Updated state with sec_filing_context populated
    """
    agent_start = time.time()
    ticker = state.get("ticker", "")

    # Default empty context (graceful degradation)
    empty_context = {
        "risk_factors_context": "Not available",
        "mda_context": "Not available",
        "filing_date": "",
        "source_url": "",
        "available": False,
        "uploaded_context": "Not available",
    }

    if not ticker:
        state["sec_filing_context"] = empty_context
        return state

    print(f"\n[Document Retriever Agent] Fetching SEC filing context for {ticker}...")

    try:
        from services.document_store import DocumentStore
        from services.sec_edgar import fetch_filing_urls, download_filing, extract_sections
        from services.document_registry import register_document
        from services.pdf_extractor import extract_pdf_bytes
        from services.mongo_client import get_gridfs

        store = DocumentStore()
        document_sources = []

        # Check if we already have recent filings cached
        if store.has_recent_filing(ticker):
            print(f"[Document Retriever Agent] Using cached filings for {ticker}")
        else:
            # Fetch and store new filings
            print(f"[Document Retriever Agent] Fetching filings from SEC EDGAR...")
            filings = fetch_filing_urls(ticker, filing_type="10-K", count=2)

            if not filings:
                print(f"[Document Retriever Agent] No 10-K filings found for {ticker}")
            else:
                for filing in filings:
                    print(f"[Document Retriever Agent] Downloading filing from {filing.get('filing_date', 'unknown date')}...")
                    text = download_filing(filing["url"])
                    if not text:
                        continue

                    sections = extract_sections(text)
                    if sections:
                        stored_chunks = store.add_sec_filing_chunks(
                            ticker=ticker,
                            sections=sections,
                            filing_date=filing.get("filing_date", ""),
                        )
                        print(f"[Document Retriever Agent] Stored {len(sections)} sections from {filing.get('filing_date', '')}")
                        doc_entry = register_document({
                            "source_type": "sec_filing",
                            "ticker": ticker,
                            "analysis_id": state.get("_analysis_id", ""),
                            "title": f"{ticker} 10-K",
                            "source_url": filing.get("url", ""),
                            "filing_date": filing.get("filing_date", ""),
                            "chunks": stored_chunks,
                        })
                        document_sources.append(doc_entry)

        # Optional: ingest user uploaded PDF for this analysis
        upload_info = state.get("uploaded_document", {}) or {}
        gridfs_file_id = upload_info.get("gridfs_file_id", "")
        if gridfs_file_id:
            print(f"[Document Retriever Agent] Processing uploaded document: {upload_info.get('filename', 'unknown')}")
            gridfs = get_gridfs()
            file_bytes = gridfs.open_download_stream(gridfs_file_id).read()
            pdf_text = extract_pdf_bytes(file_bytes)
            if pdf_text:
                doc_entry = register_document({
                    "source_type": "user_pdf",
                    "ticker": ticker,
                    "analysis_id": state.get("_analysis_id", ""),
                    "title": upload_info.get("filename", "Uploaded PDF"),
                    "filename": upload_info.get("filename", "uploaded.pdf"),
                    "gridfs_file_id": gridfs_file_id,
                    "chunks": 0,
                })
                uploaded_chunks = store.add_user_document_chunks(
                    analysis_id=state.get("_analysis_id", ""),
                    ticker=ticker,
                    doc_id=doc_entry.get("id", ""),
                    filename=upload_info.get("filename", "uploaded.pdf"),
                    content=pdf_text,
                    uploaded_at=upload_info.get("uploaded_at", ""),
                )
                if uploaded_chunks > 0:
                    doc_entry["chunks"] = uploaded_chunks
                    register_document(doc_entry)
                    document_sources.append(doc_entry)

        # Query for relevant context
        risk_query = f"What are the key risk factors for {ticker}?"
        mda_query = f"What is the management discussion and outlook for {ticker}?"
        upload_query = f"Summarize important fundamental and risk insights for {ticker}"

        risk_chunks = store.query(ticker, risk_query, n_results=3, section_filter="risk_factors")
        mda_chunks = store.query(ticker, mda_query, n_results=3, section_filter="mda")
        uploaded_chunks = store.query_user_documents(
            analysis_id=state.get("_analysis_id", ""),
            ticker=ticker,
            query_text=upload_query,
            n_results=3,
        )

        # Build context strings
        risk_context = "\n\n".join(c.text for c in risk_chunks) if risk_chunks else "Not available"
        mda_context = "\n\n".join(c.text for c in mda_chunks) if mda_chunks else "Not available"
        uploaded_context = "\n\n".join(c.text for c in uploaded_chunks) if uploaded_chunks else "Not available"

        # Get filing metadata
        filing_date = ""
        source_url = ""
        if risk_chunks:
            filing_date = risk_chunks[0].metadata.get("filing_date", "")
        elif mda_chunks:
            filing_date = mda_chunks[0].metadata.get("filing_date", "")

        # Truncate context to reasonable size for prompt inclusion
        max_context_len = 3000
        if len(risk_context) > max_context_len:
            risk_context = risk_context[:max_context_len] + "\n...[truncated]"
        if len(mda_context) > max_context_len:
            mda_context = mda_context[:max_context_len] + "\n...[truncated]"
        if len(uploaded_context) > max_context_len:
            uploaded_context = uploaded_context[:max_context_len] + "\n...[truncated]"

        if (risk_chunks or mda_chunks) and not any(d.get("source_type") == "sec_filing" for d in document_sources):
            from services.document_registry import register_document
            doc_entry = register_document({
                "source_type": "sec_filing",
                "ticker": ticker,
                "analysis_id": state.get("_analysis_id", ""),
                "title": f"{ticker} 10-K",
                "filing_date": filing_date,
                "chunks": len(risk_chunks) + len(mda_chunks),
                "source_url": source_url,
            })
            document_sources.append(doc_entry)

        state["sec_filing_context"] = {
            "risk_factors_context": risk_context,
            "mda_context": mda_context,
            "uploaded_context": uploaded_context,
            "filing_date": filing_date,
            "source_url": source_url,
            "available": bool(risk_chunks or mda_chunks or uploaded_chunks),
            "num_risk_chunks": len(risk_chunks),
            "num_mda_chunks": len(mda_chunks),
            "num_uploaded_chunks": len(uploaded_chunks),
        }
        state["document_sources"] = document_sources

        agent_time = time.time() - agent_start
        print(f"[Document Retriever Agent] Complete in {agent_time:.1f}s. "
              f"Risk chunks: {len(risk_chunks)}, MD&A chunks: {len(mda_chunks)}, Uploaded chunks: {len(uploaded_chunks)}")

    except ImportError as e:
        print(f"[Document Retriever Agent] Missing dependency: {e}")
        print("[Document Retriever Agent] Install with: pip install chromadb openai beautifulsoup4")
        state["sec_filing_context"] = empty_context

    except Exception as e:
        agent_time = time.time() - agent_start
        print(f"[Document Retriever Agent] Error after {agent_time:.1f}s: {e}")
        state["sec_filing_context"] = empty_context

    return state

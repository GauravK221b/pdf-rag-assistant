
import streamlit as st
import hashlib
import io

from rag import build_rag_pipeline, generate_answer, model


st.set_page_config(
    page_title="PDF RAG Assistant",
    page_icon="📚",
    layout="wide"
)


st.title("📚 PDF RAG Assistant")
st.write("Upload a PDF and ask questions based on its content.")


uploaded_file = st.file_uploader(
    "Upload your PDF",
    type=["pdf"]
)


if uploaded_file is not None:

    pdf_bytes = uploaded_file.getvalue()

    pdf_id = hashlib.md5(pdf_bytes).hexdigest()

    # Process PDF only when a new PDF is uploaded
    if st.session_state.get("pdf_id") != pdf_id:

        with st.spinner("Processing PDF..."):

            try:
                index, store_chunk = build_rag_pipeline(
                    io.BytesIO(pdf_bytes)
                )

                st.session_state.pdf_id = pdf_id
                st.session_state.index = index
                st.session_state.store_chunk = store_chunk

                st.session_state.answer = None
                st.session_state.sources = None
                st.session_state.provider = None

                st.success("PDF processed successfully!")

            except Exception as e:
                st.error(f"PDF processing failed: {e}")

                st.stop()

    # Question input
    question = st.text_input(
        "Ask a question about your PDF"
    )

    if st.button("Get Answer"):

        if not question.strip():

            st.warning("Please enter a question.")

        else:

            with st.spinner("Generating answer..."):

                try:
                    answer, sources, provider = generate_answer(
                        question,
                        model,
                        st.session_state.index,
                        st.session_state.store_chunk
                    )

                    st.session_state.answer = answer
                    st.session_state.sources = sources
                    st.session_state.provider = provider

                except Exception as e:

                    st.error(str(e))

    # Display answer
    if st.session_state.get("answer"):

        st.subheader("Answer")

        st.write(st.session_state.answer)

        # Display LLM provider
        st.caption(
            f"Generated using: {st.session_state.provider}"
        )

        # Display source pages
        sources = st.session_state.sources

        pages = sorted(set(
            result["page_no"] for result in sources
        ))

        st.subheader("Source Pages")

        st.write(", ".join(map(str, pages)))

        # Display retrieved passages
        with st.expander("View retrieved PDF passages"):

            for i, result in enumerate(sources):

                st.markdown(
                    f"**Passage {i + 1} | Page {result['page_no']}**"
                )

                st.write(result["text"])

                st.caption(
                    f"Similarity score: {result['score']:.4f}"
                )

                st.divider()

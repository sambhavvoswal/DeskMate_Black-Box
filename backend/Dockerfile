FROM python:3.10-slim

# Create user with UID 1000 to run on Hugging Face Spaces safely
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# Hugging Face sets PORT environment variable, which defaults to 7860
EXPOSE 7860

CMD ["python", "app.py"]

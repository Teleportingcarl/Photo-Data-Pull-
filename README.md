# Photo Data Puller

A lightweight tool for checking whether a JPEG likely came from a real-world camera lens. Includes:

- **CLI**: quick batch analysis with JSON output.
- **Drop UI**: Streamlit app with drag-and-drop uploader and readable results.

## Quick start

```bash
python photo_data_puller.py path/to/photo.jpg
# or analyze multiple images at once
python photo_data_puller.py first.jpg second.jpg
```

## Streamlit interface

```bash
pip install streamlit
streamlit run streamlit_app.py
```

Upload a JPEG and the app will show device hints, resolution, timestamps, GPS indicators, and a JSON report.

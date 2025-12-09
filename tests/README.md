# Sejm Highlights - Test Suite

Comprehensive test suite for the Sejm Highlights AI pipeline.

## Running Tests

### Run all tests:
```bash
pytest
```

### Run specific test file:
```bash
pytest tests/test_config.py
pytest tests/test_features.py
pytest tests/test_scoring.py
pytest tests/test_selection.py
```

### Run with verbose output:
```bash
pytest -v
```

### Run with coverage:
```bash
pytest --cov=pipeline --cov-report=html
```

## Test Organization

### `test_config.py`
Tests for configuration loading and validation:
- YAML configuration loading
- Config parameter validation
- Weight sum checks
- Constraint validation

### `test_features.py`
Tests for feature extraction (Stage 4):
- Acoustic feature extraction (RMS, spectral features, ZCR)
- Prosodic feature extraction (speech rate, pauses)
- Empty/silence handling
- Edge cases

### `test_scoring.py`
Tests for AI scoring system (Stage 5):
- Composite score calculation
- Pre-filtering logic
- GPT fallback mechanisms
- Score normalization and boundaries

### `test_selection.py`
Tests for clip selection algorithm (Stage 6):
- Duration filtering
- Greedy selection with NMS
- Smart merging of adjacent clips
- Temporal coverage optimization
- Duration adjustment

## Test Markers

Use pytest markers to run specific test categories:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run GPU tests only (requires CUDA)
pytest -m gpu

# Skip tests that require AI models
pytest -m "not requires_models"
```

## Fixtures

Common test fixtures are defined in `conftest.py`:

- `temp_dir`: Temporary directory for test files
- `sample_config`: Sample configuration for testing
- `sample_audio`: Generated audio array (5s, 16kHz)
- `sample_transcript`: Mock transcript with word timings
- `sample_features`: Mock feature dictionary
- `sample_segments`: Mock scored segments for selection

## Adding New Tests

When adding new tests:

1. Use descriptive test names starting with `test_`
2. Add docstrings explaining what is being tested
3. Use appropriate fixtures from `conftest.py`
4. Mark tests with appropriate markers (unit, integration, slow, gpu, requires_models)
5. Test both success and failure cases
6. Test edge cases (empty inputs, invalid data, etc.)

Example:
```python
@pytest.mark.unit
def test_my_new_feature(sample_config):
    \"\"\"Test that my new feature works correctly\"\"\"
    # Arrange
    stage = MyStage(sample_config)

    # Act
    result = stage.process_something()

    # Assert
    assert result is not None
    assert result > 0
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines. Configure your CI to:

1. Install dependencies: `pip install -r requirements.txt`
2. Run tests: `pytest`
3. Generate coverage reports: `pytest --cov=pipeline --cov-report=xml`

## Troubleshooting

### Missing spaCy model
```bash
python -m spacy download pl_core_news_lg
```

### Missing CUDA for GPU tests
GPU tests will be skipped automatically if CUDA is not available.

### OpenAI API key for GPT tests
GPT-related tests will use fallback scoring if `OPENAI_API_KEY` is not set in `.env`.

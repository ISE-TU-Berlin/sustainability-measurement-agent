# Report File Organization Changes

## Summary

Implemented a clear separation between location-level and file-level parameters for report organization:

### Key Changes

1. **Location Template** (subdirectories allowed)
   - Can use RunData fields: `${startTime}`, `${endTime}`, `${runHash}`, etc.
   - Can use location_metadata: any custom keys passed via `run(location_metadata={...})`
   - Example: `reports/${experiment_id}/${cluster_name}/${startTime}_${runHash}/`

2. **Filename Template** (flat names only)
   - Can use RunData fields and `${name}` (required)
   - Can use trigger function return values (file-level metadata)
   - **Cannot contain path separators** (`/`, `\`, or `os.path.sep`)
   - Validation raises clear error if paths detected
   - Example: `${name}.csv` or `${name}_${batch_size}.csv`

3. **Location Metadata Flow**
   - Passed to `agent.run(location_metadata={...})`
   - Available in location template
   - Persisted in `run_metadata.json` under `"run_extras"` key
   - Loaded automatically when reading reports

4. **File Metadata (from Trigger Function)**
   - Returned from trigger function
   - Available in filename template only
   - For file-specific metadata

## API Changes

### Before
```python
agent.run(
    trigger=my_workload,
    run_extras={"experiment_id": "exp_123"}  # Confusing name!
)
```

### After
```python
agent.run(
    trigger=my_workload,  # Returns file_metadata dict
    location_metadata={   # Clear: used for location template
        "experiment_id": "exp_123",
        "cluster_name": "prod"
    }
)
```

## Config Example

```yaml
report:
  location: reports/${experiment_id}/${startTime}_${runHash}/
  filename: "${name}.csv"  # No path separators allowed!
```

## Benefits

1. ✅ All report files stay in same directory
2. ✅ Clear separation: location vs filename
3. ✅ Flexible organization via location_metadata
4. ✅ Validation prevents accidental nesting
5. ✅ Round-trip persistence (save & load)
6. ✅ Backwards compatible (location_metadata optional)
7. ✅ **Self-documenting parameter names** (location_metadata vs file_metadata)

## Migration Guide

If your config has:
```yaml
filename: "${startTime}_${runHash}/${name}.csv"
```

Change to:
```yaml
location: reports/${startTime}_${runHash}/
filename: "${name}.csv"
```

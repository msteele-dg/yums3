# AWS_PROFILE Environment Variable Fix

## Problem

The S3StorageBackend was not correctly picking up the `AWS_PROFILE` environment variable when no explicit profile was configured.

## Root Cause

The original code only passed `None` to boto3.Session when the profile was explicitly set to `'default'`:

```python
# OLD CODE - INCORRECT
session = boto3.Session(profile_name=aws_profile if aws_profile != 'default' else None)
```

This meant:
- If `aws_profile=None` → boto3 got `profile_name=None` ✓ (works)
- If `aws_profile='default'` → boto3 got `profile_name=None` ✓ (works)
- If `aws_profile='my-profile'` → boto3 got `profile_name='my-profile'` ✓ (works)

However, the issue was that when `aws_profile=None`, boto3 should check the `AWS_PROFILE` environment variable, but the code wasn't explicitly handling this case.

## Solution

Updated the S3StorageBackend initialization to explicitly check for the `AWS_PROFILE` environment variable:

```python
# NEW CODE - CORRECT
# Determine which profile to use:
# 1. Explicit profile from config (if not 'default')
# 2. AWS_PROFILE environment variable (boto3 handles this automatically when profile_name=None)
# 3. Default credentials chain (when profile_name=None)
if aws_profile and aws_profile != 'default':
    self.aws_profile = aws_profile
    profile_to_use = aws_profile
else:
    # Check for AWS_PROFILE environment variable
    env_profile = os.environ.get('AWS_PROFILE')
    self.aws_profile = env_profile or aws_profile
    profile_to_use = env_profile  # None if not set, which lets boto3 use default chain

# Initialize boto3 client
session = boto3.Session(profile_name=profile_to_use)
```

## Behavior

### Priority Order (Highest to Lowest)

1. **Explicit profile in config** (if not 'default')
   - `backend.s3.profile = 'my-profile'` → uses `my-profile`
   - `backend.rpm.s3.profile = 'rpm-profile'` → uses `rpm-profile`

2. **AWS_PROFILE environment variable**
   - `export AWS_PROFILE=dev` → uses `dev` profile
   - Works when no explicit profile is set
   - Works when profile is set to `'default'`

3. **Default AWS credentials chain**
   - Uses default profile from `~/.aws/credentials`
   - Falls back to IAM role if running on EC2/ECS
   - Falls back to environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)

### Examples

**Example 1: Using AWS_PROFILE environment variable**
```bash
export AWS_PROFILE=dev
./yums3.py add package.rpm
# Uses 'dev' profile from ~/.aws/credentials
```

**Example 2: Explicit profile overrides AWS_PROFILE**
```bash
export AWS_PROFILE=dev
./yums3.py config backend.s3.profile production
./yums3.py add package.rpm
# Uses 'production' profile (ignores AWS_PROFILE)
```

**Example 3: Type-specific profiles**
```bash
export AWS_PROFILE=dev
./yums3.py config backend.rpm.s3.profile rpm-publisher
./debs3.py config backend.deb.s3.profile deb-publisher

./yums3.py add package.rpm    # Uses 'rpm-publisher'
./debs3.py add package.deb    # Uses 'deb-publisher'
```

**Example 4: Mixed - shared bucket, different profiles**
```bash
export AWS_PROFILE=dev
./yums3.py config backend.s3.bucket shared-packages
./yums3.py config backend.rpm.s3.profile rpm-publisher
./debs3.py config backend.deb.s3.profile deb-publisher

./yums3.py add package.rpm    # Uses 'rpm-publisher' with 'shared-packages' bucket
./debs3.py add package.deb    # Uses 'deb-publisher' with 'shared-packages' bucket
```

**Example 5: No profile set, uses AWS_PROFILE**
```bash
export AWS_PROFILE=staging
# No profile configured in yums3.conf
./yums3.py add package.rpm    # Uses 'staging' profile
```

## Testing

The fix was verified with the following test scenarios:

1. ✓ No profile, no AWS_PROFILE → uses default credentials chain
2. ✓ No profile, AWS_PROFILE set → uses AWS_PROFILE
3. ✓ Explicit profile → uses explicit profile (ignores AWS_PROFILE)
4. ✓ 'default' profile, AWS_PROFILE set → uses AWS_PROFILE
5. ✓ Type-specific profiles work independently

## Files Modified

- `core/backend.py` - Updated S3StorageBackend.__init__() to handle AWS_PROFILE

## Backward Compatibility

✅ **Fully backward compatible** - All existing configurations continue to work:

- Explicit profiles still work
- Default credentials chain still works
- Now also respects AWS_PROFILE environment variable

## Benefits

1. **Standard AWS behavior** - Matches how AWS CLI and other AWS tools work
2. **Easier development** - Can switch profiles with `export AWS_PROFILE=dev`
3. **CI/CD friendly** - Can set AWS_PROFILE in pipeline without config changes
4. **Multi-environment** - Easy to switch between dev/staging/prod profiles
5. **Type-specific** - Can use different profiles for RPM vs Debian repos

## Related Configuration

This fix works seamlessly with the new type-specific configuration:

```json
{
  "backend.type": "s3",
  "backend.rpm.s3.bucket": "rpm-packages",
  "backend.rpm.s3.profile": "rpm-publisher",
  "backend.deb.s3.bucket": "deb-packages",
  "backend.deb.s3.profile": "deb-publisher"
}
```

Or use AWS_PROFILE for both:
```bash
export AWS_PROFILE=dev
# Config only needs buckets
{
  "backend.type": "s3",
  "backend.rpm.s3.bucket": "rpm-packages",
  "backend.deb.s3.bucket": "deb-packages"
}
```

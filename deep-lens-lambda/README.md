## deep-lens-lambda Lambda function
This Lambda function is used by the DeepLens project, and will be deployed to the actual
DeepLens device. It is used in conjunction with the pre-build object detection model,
which is available at *s3://deeplens-managed-resources/models/SSDresNet50*.

### Configuration
In order to use this application, you will need to perform the following
customizations to the code.
* Update *write_image_to_s3* function to use your S3 bucket name and key. Note that the Alexa application must match the values used here in order to detect any birds that are seen.

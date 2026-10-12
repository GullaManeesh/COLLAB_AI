from app.config.settings import settings

print("Application:", settings.APP_NAME)
print("Version:", settings.APP_VERSION)
print("Environment:", settings.ENVIRONMENT)
print("MongoDB database:", settings.MONGODB_DB_NAME)
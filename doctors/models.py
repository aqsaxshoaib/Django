from django.db import models
from django.utils import timezone

class Country(models.Model):
    name = models.CharField(max_length=255)
    status = models.SmallIntegerField()
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'countries'

class Canton(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'cantons'

class City(models.Model):
    canton = models.ForeignKey(Canton, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'cities'

class Language(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255, null=True, blank=True)
    translation_status = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'languages'

class Specialties(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=255, default='1')
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'specialties'

class Expertise(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=255, default='1')
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'expertises'

class Patient(models.Model):
    id = models.BigAutoField(primary_key=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    country = models.ForeignKey(
        'Country',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='country'
    )

    city = models.ForeignKey(
        'City',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='city'
    )
    languages = models.ManyToManyField(
        'Language',
        db_table='user_languages',
        blank=True
    )
    address = models.CharField(max_length=255, null=True, blank=True)
    postal_code = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=255, null=True, blank=True)
    birth_date = models.CharField(max_length=255, null=True, blank=True)
    gender = models.CharField(max_length=255, null=True, blank=True)
    profile_pic = models.CharField(max_length=255, null=True, blank=True)
    about_me = models.CharField(max_length=255, null=True, blank=True)
    insurance_name = models.CharField(max_length=255, null=True, blank=True)
    insurance_number = models.CharField(max_length=255, null=True, blank=True)
    extension_code = models.CharField(max_length=255, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    updated_at = models.DateTimeField(null=True, blank=True, auto_now=True)

    def clean_country(self):
        """Get normalized country name"""
        if self.country:
            return self.country.name.strip().lower()
        return None

    def clean_city(self):
        """Get normalized city name"""
        if self.city:
            return self.city.name.strip().lower()
        return None

    class Meta:
        db_table = 'patients'

    def __str__(self):
        return f"{self.first_name} {self.last_name}" if self.first_name else f"Patient {self.id}"


class User(models.Model):
    # Enum for service type
    SERVICE_TYPE_CHOICES = [
        ('onsite', 'On-site'),
        ('remote', 'Remote'),
        ('both', 'Both')
    ]

    # Primary key
    id = models.BigAutoField(primary_key=True)

    # Personal Information
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(max_length=255, default='user')
    gender = models.CharField(max_length=255, null=True, blank=True)
    age = models.DateField(null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)

    # Location Information
    country = models.ForeignKey(
        'Country',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='country'
    )

    city = models.ForeignKey(
        'City',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='city'
    )
    languages = models.ManyToManyField(
        'Language',
        db_table='user_languages',  # Creates a join table
        blank=True
    )
    Speaking_Languages = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    house_number = models.CharField(max_length=255, null=True, blank=True)
    postal_code = models.CharField(max_length=255, null=True, blank=True)
    zip_code = models.CharField(max_length=255, null=True, blank=True)
    latitude = models.CharField(max_length=255, null=True, blank=True)
    longitude = models.CharField(max_length=255, null=True, blank=True)

    # Contact Information
    phone = models.CharField(max_length=255, null=True, blank=True)
    hin_email = models.CharField(max_length=255, null=True, blank=True)
    fax_phone_number = models.CharField(max_length=255, null=True, blank=True)
    fax_number = models.CharField(max_length=255, null=True, blank=True)
    web_url = models.CharField(max_length=255, null=True, blank=True)

    # Professional Information
    speciality = models.CharField(max_length=255, null=True, blank=True)
    specialties = models.ForeignKey(
        'Specialties',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='specialties'
    )

    experties = models.ForeignKey(
        'Expertise',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='sxpertise'
    )
    service_type = models.CharField(
        max_length=10,
        choices=SERVICE_TYPE_CHOICES,
        default='onsite'
    )
    fees = models.CharField(max_length=255, null=True, blank=True)
    payment_method = models.CharField(max_length=255, null=True, blank=True)

    # Additional Professional Details
    Access_info = models.CharField(max_length=255, null=True, blank=True)
    healthcare_professional_info = models.TextField(null=True, blank=True)
    about_me = models.TextField(null=True, blank=True)

    # Profile and Media
    profile_pic = models.CharField(max_length=255, null=True, blank=True)

    # System and Account Management
    otp = models.CharField(max_length=255, null=True, blank=True)
    is_online = models.CharField(max_length=255, default='1')
    is_active = models.CharField(max_length=255, default='0')
    token = models.CharField(max_length=255, default='0')
    status = models.CharField(max_length=255, default='0')
    referral_code = models.CharField(max_length=255, null=True, blank=True)

    # Institutional Information
    institute_id = models.BigIntegerField(null=True, blank=True)
    zefix_ide = models.CharField(max_length=255, null=True, blank=True)
    extension_code = models.BigIntegerField(null=True, blank=True)

    # Financial Information
    wallet = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Notification Preferences
    sms_reminder = models.BooleanField(null=True)
    sms_confirmation = models.BooleanField(null=True)

    # Additional Fields
    reviews = models.ForeignKey(
        'Review',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='reviwes',
        related_name='reviewed_users'
    )

    patient_status = models.CharField(max_length=255, null=True, blank=True)

    # Boost-related Fields
    is_boosted = models.BooleanField(default=False)
    boost_end_at = models.DateTimeField(null=True, blank=True)

    # Timestamp Fields
    created_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    updated_at = models.DateTimeField(null=True, blank=True, auto_now=True)
    language_ids = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_column='language'  # Maps to your existing column
    )

    @property
    def languages(self):
        """Get Language objects from comma-separated IDs"""
        if not self.language_ids:
            return Language.objects.none()

        ids = [int(id_str) for id_str in self.language_ids.split(',')]
        return Language.objects.filter(id__in=ids)

    @languages.setter
    def languages(self, language_objs):
        """Store Language objects as comma-separated IDs"""
        self.language_ids = ','.join(str(lang.id) for lang in language_objs)

    @property
    def coordinates(self):
        """Get coordinates as numeric values if available"""
        try:
            return (float(self.latitude), float(self.longitude))
        except (TypeError, ValueError):
            return None

    def valid_geo_location(self):
        """Check if user has valid geo coordinates"""
        return self.coordinates and all(
            -90 <= self.coordinates[0] <= 90,
            -180 <= self.coordinates[1] <= 180
        )

    def clean_country(self):
        """Get normalized country name"""
        if self.country:
            return self.country.name.strip().lower()
        return None

    def clean_city(self):
        """Get normalized city name"""
        if self.city:
            return self.city.name.strip().lower()
        return None


    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        """String representation of the user"""
        return f"{self.first_name} {self.last_name}" if self.first_name and self.last_name else self.email or str(
            self.id)

    def save(self, *args, **kwargs):
        """
        Override save method to set created_at and updated_at
        """
        if not self.id:
            self.created_at = timezone.now()
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    patient_name = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    rating = models.IntegerField()
    comments = models.TextField()
    status = models.CharField(max_length=20, choices=[
        ('accepted', 'Accepted'),
        ('canceled', 'Canceled'),
        ('pending', 'Pending')
    ], default='pending')
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'reviews'
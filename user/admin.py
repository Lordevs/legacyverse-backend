from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile, PasswordResetToken, ChildhoodImage


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'fullname', 'username', 'is_verified', 'is_active', 'created_at')
    list_filter = ('is_verified', 'is_active', 'is_staff', 'created_at')
    search_fields = ('email', 'fullname', 'username')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('fullname', 'username')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'fullname', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('username', 'created_at', 'updated_at')


class ChildhoodImageInline(admin.TabularInline):
    """
    Inline admin for childhood images
    """
    model = ChildhoodImage
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'location', 'joined_date', 'created_at')
    list_filter = ('created_at', 'updated_at', 'joined_date')
    search_fields = ('user__email', 'user__fullname', 'location')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ChildhoodImageInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'image', 'bio', 'location', 'website', 'joined_date')
        }),
        ('Life Details', {
            'fields': ('education_json', 'hobbies', 'early_childhood')
        }),
        ('JSON Data', {
            'fields': ('family_json', 'community_json', 'professional_experience_json', 'accomplishment_json'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(ChildhoodImage)
class ChildhoodImageAdmin(admin.ModelAdmin):
    list_display = ('profile', 'caption', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('profile__user__email', 'profile__user__fullname', 'caption')
    readonly_fields = ('created_at',)


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at', 'is_used')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__email', 'user__fullname')
    readonly_fields = ('token', 'created_at')

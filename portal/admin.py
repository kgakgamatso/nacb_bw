from django.contrib import admin

from .models import (DataRequest, Tender, Vacancy, FAQ, AuditLog, Communication, ContactMessage, GalleryAlbum, GalleryImage, LeadershipMember,
                     NewsletterSubscriber, NewsPost, Notification, Page, Resource)


@admin.action(description="Publish selected")
def publish(modeladmin, request, qs):
    qs.update(status="published")


@admin.action(description="Archive selected")
def archive(modeladmin, request, qs):
    qs.update(status="archived")


class PublishableAdmin(admin.ModelAdmin):
    actions = [publish, archive]
    list_filter = ["status"]


@admin.register(Page)
class PageAdmin(PublishableAdmin):
    list_display = ["title", "slug", "status", "show_in_footer", "order", "updated_at"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "body"]


@admin.register(NewsPost)
class NewsAdmin(PublishableAdmin):
    list_display = ["title", "category", "status", "publish_at", "featured"]
    list_filter = ["status", "category", "featured"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "summary", "body"]
    date_hierarchy = "publish_at"
    raw_id_fields = ["author"]

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(Resource)
class ResourceAdmin(PublishableAdmin):
    list_display = ["title", "category", "year", "status", "downloads"]
    list_filter = ["status", "category"]
    search_fields = ["title"]


class ImageInline(admin.TabularInline):
    model = GalleryImage
    extra = 3


@admin.register(GalleryAlbum)
class AlbumAdmin(PublishableAdmin):
    list_display = ["title", "status", "publish_at"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ImageInline]


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ["question", "category", "order", "published"]
    list_filter = ["category", "published"]
    list_editable = ["order", "published"]


@admin.register(LeadershipMember)
class LeadershipAdmin(admin.ModelAdmin):
    list_display = ["name", "position", "group", "order"]
    list_editable = ["order"]


@admin.register(NewsletterSubscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ["email", "name", "active", "created_at"]
    list_filter = ["active"]
    search_fields = ["email"]


@admin.register(ContactMessage)
class ContactAdmin(admin.ModelAdmin):
    list_display = ["subject", "name", "category", "created_at", "resolved"]
    list_filter = ["category", "resolved"]


@admin.register(AuditLog)
class AuditAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor", "action", "object_repr", "ip_address"]
    list_filter = ["action", "object_type"]
    search_fields = ["object_repr", "actor__email", "action"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Notification)
admin.site.register(Communication)


@admin.register(Vacancy)
class VacancyAdmin(PublishableAdmin):
    list_display = ["title", "reference", "employment_type", "closing_date", "status"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "reference"]


@admin.register(Tender)
class TenderAdmin(PublishableAdmin):
    list_display = ["reference", "title", "category", "closing_date", "status"]
    list_filter = ["status", "category"]
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ["title", "reference"]


@admin.register(DataRequest)
class DataRequestAdmin(admin.ModelAdmin):
    list_display = ["email", "request_type", "status", "created_at", "due_date"]
    list_filter = ["status", "request_type"]

import { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Page } from '../../components/Layout';
import { Button, EmptyState, ErrorState, LinkButton, ListSkeleton, Photo } from '../../components/ui';
import { useToast } from '../../components/ToastContext';
import { ApiError, errorMessage } from '../../api/client';
import { uploadPhoto } from '../../api/endpoints';
import {
  useAdminProducts,
  useCreateProduct,
  useProduct,
  useUpdateProduct,
} from '../../api/queries';
import type { Product, ProductCreate } from '../../api/types';
import { PRODUCT_CATEGORIES, categoryLabel, isProductCategory } from '../../lib/categories';
import { toMoneyString, toWeightString } from '../../lib/money';
import { hasErrors, validateProductForm } from '../../lib/validation';
import type { CheckoutErrors, ProductFormValues } from '../../lib/validation';
import { haptic } from '../../telegram/webapp';

/** Сколько товаров просматриваем, разыскивая редактируемый (GET /admin/products/{id} контрактом не предусмотрен). */
const LOOKUP_LIMIT = 50;

/** Разрешённые типы фото — бэкенд всё равно перепроверяет по сигнатуре байтов. */
const ALLOWED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_PHOTO_MB = 5;

const EMPTY_FORM: ProductFormValues = {
  name: '',
  description: '',
  category: '',
  pricePerKg: '',
  stockKg: '',
  photoUrl: '',
  isActive: true,
};

function toFormValues(product: Product): ProductFormValues {
  return {
    name: product.name,
    description: product.description ?? '',
    category: product.category ?? '',
    pricePerKg: product.price_per_kg,
    stockKg: product.stock_kg,
    photoUrl: product.photo_url ?? '',
    isActive: product.is_active,
  };
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <span className="field__error">{message}</span>;
}

/* ------------------------------ Форма товара ------------------------------ */

function ProductForm({ product }: { product: Product | null }) {
  const navigate = useNavigate();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);

  const [values, setValues] = useState<ProductFormValues>(() =>
    product ? toFormValues(product) : EMPTY_FORM,
  );
  const [errors, setErrors] = useState<CheckoutErrors>({});
  const [uploading, setUploading] = useState(false);

  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();
  const saving = createProduct.isPending || updateProduct.isPending;

  const setField = <K extends keyof ProductFormValues>(key: K, value: ProductFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
    setErrors((current) => {
      if (!(key in current)) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  };

  const handleFile = async (file: File) => {
    if (!ALLOWED_PHOTO_TYPES.includes(file.type)) {
      toast.error('Нужен файл JPEG, PNG или WebP');
      return;
    }
    if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
      toast.error('Файл больше ' + MAX_PHOTO_MB + ' МБ');
      return;
    }

    setUploading(true);
    try {
      const response = await uploadPhoto(file);
      setField('photoUrl', response.photo_url);
      haptic.notification('success');
      toast.success('Фото загружено');
    } catch (uploadError) {
      haptic.notification('error');
      toast.error(errorMessage(uploadError));
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const handleSubmit = async () => {
    const nextErrors = validateProductForm(values);
    setErrors(nextErrors);
    if (hasErrors(nextErrors)) {
      haptic.notification('error');
      toast.error('Проверьте заполнение формы');
      return;
    }

    const description = values.description.trim();
    const payload: ProductCreate = {
      name: values.name.trim(),
      description: description === '' ? null : description,
      category: values.category === '' ? null : values.category,
      price_per_kg: toMoneyString(values.pricePerKg),
      stock_kg: toWeightString(values.stockKg),
      photo_url: values.photoUrl === '' ? null : values.photoUrl,
      is_active: values.isActive,
    };

    try {
      if (product) {
        await updateProduct.mutateAsync({ id: product.id, payload });
        toast.success('Товар сохранён');
      } else {
        await createProduct.mutateAsync(payload);
        toast.success('Товар добавлен');
      }
      haptic.notification('success');
      navigate('/admin/products');
    } catch (saveError) {
      haptic.notification('error');
      toast.error(errorMessage(saveError));
    }
  };

  return (
    <>
      <div className="stack">
        <div className="panel stack">
          <div className="field">
            <label className="field__label" htmlFor="product-name">
              Название
            </label>
            <input
              id="product-name"
              className={'input' + (errors.name ? ' has-error' : '')}
              type="text"
              placeholder="Например, говядина"
              value={values.name}
              onChange={(event) => setField('name', event.target.value)}
            />
            <FieldError message={errors.name} />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="product-description">
              Описание
            </label>
            <textarea
              id="product-description"
              className={'textarea' + (errors.description ? ' has-error' : '')}
              placeholder="Из чего состоит, как хранить, для каких собак подходит"
              value={values.description}
              onChange={(event) => setField('description', event.target.value)}
            />
            <FieldError message={errors.description} />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="product-category">
              Категория
            </label>
            <select
              id="product-category"
              className="select"
              value={values.category}
              onChange={(event) => {
                const value = event.target.value;
                setField('category', isProductCategory(value) ? value : '');
              }}
            >
              <option value="">— без категории —</option>
              {PRODUCT_CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {categoryLabel(category)}
                </option>
              ))}
            </select>
            <span className="field__hint">Необязательно — помогает покупателю в каталоге.</span>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="product-price">
              Цена за килограмм, ₽
            </label>
            <input
              id="product-price"
              className={'input' + (errors.pricePerKg ? ' has-error' : '')}
              type="text"
              inputMode="decimal"
              placeholder="890"
              value={values.pricePerKg}
              onChange={(event) => setField('pricePerKg', event.target.value)}
            />
            <FieldError message={errors.pricePerKg} />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="product-stock">
              Остаток, кг
            </label>
            <input
              id="product-stock"
              className={'input' + (errors.stockKg ? ' has-error' : '')}
              type="text"
              inputMode="decimal"
              placeholder="12.5"
              value={values.stockKg}
              onChange={(event) => setField('stockKg', event.target.value)}
            />
            <FieldError message={errors.stockKg} />
          </div>
        </div>

        <div className="panel stack">
          <h2>Фотография</h2>

          <div className="photo-preview">
            <Photo url={values.photoUrl === '' ? null : values.photoUrl} alt="Фото товара" />
            {uploading ? (
              <div className="photo-preview__overlay">
                <span className="btn__spinner" aria-hidden="true" />
                Загружаем…
              </div>
            ) : null}
          </div>

          <input
            ref={fileInput}
            className="visually-hidden"
            id="product-photo"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={uploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />

          <div className="row">
            <Button
              variant="secondary"
              block
              loading={uploading}
              disabled={uploading}
              onClick={() => fileInput.current?.click()}
            >
              {values.photoUrl === '' ? 'Загрузить фото' : 'Заменить фото'}
            </Button>
            {values.photoUrl === '' ? null : (
              <Button variant="danger" disabled={uploading} onClick={() => setField('photoUrl', '')}>
                Убрать
              </Button>
            )}
          </div>
          <span className="field__hint">JPEG, PNG или WebP, до {MAX_PHOTO_MB} МБ.</span>
        </div>

        <div className="panel">
          <label className="checkbox" htmlFor="product-active">
            <input
              id="product-active"
              type="checkbox"
              checked={values.isActive}
              onChange={(event) => setField('isActive', event.target.checked)}
            />
            <span>
              <span style={{ fontWeight: 600 }}>Показывать в каталоге</span>
              <span className="field__hint" style={{ display: 'block' }}>
                Снимите галочку, чтобы временно скрыть товар от покупателей.
              </span>
            </span>
          </label>
        </div>
      </div>

      <div className="sticky-bar">
        <Button
          block
          loading={saving}
          disabled={saving || uploading}
          onClick={() => void handleSubmit()}
        >
          {product ? 'Сохранить изменения' : 'Добавить товар'}
        </Button>
      </div>
    </>
  );
}

/* --------------------------- Загрузка для режима edit ---------------------- */

function EditProductLoader({ productId }: { productId: number }) {
  // Отдельного GET /admin/products/{id} в контракте нет: ищем товар в админском
  // списке (там видны и скрытые), а если не нашли — пробуем публичную карточку.
  const lookup = useAdminProducts({ include_inactive: true, limit: LOOKUP_LIMIT, offset: 0 });
  const fromList = lookup.data?.items.find((item) => item.id === productId);
  const lookupSettled = lookup.isSuccess || lookup.isError;
  const fallback = useProduct(lookupSettled && !fromList ? productId : 0);
  const product = fromList ?? fallback.data;

  if (product) {
    return <ProductForm key={product.id} product={product} />;
  }

  if (!lookupSettled || fallback.isPending) {
    return <ListSkeleton count={4} />;
  }

  if (fallback.isError) {
    const apiError = fallback.error instanceof ApiError ? fallback.error : null;
    const missing = Boolean(
      apiError && (apiError.isNotFound || apiError.code === 'product_unavailable'),
    );
    if (!missing) {
      return (
        <ErrorState
          message={errorMessage(fallback.error)}
          onRetry={() => {
            void lookup.refetch();
            void fallback.refetch();
          }}
        />
      );
    }
  }

  return (
    <EmptyState
      icon="🔎"
      title="Товар не найден"
      text="Возможно, он был удалён или скрыт очень давно."
      action={<LinkButton to="/admin/products">К списку товаров</LinkButton>}
    />
  );
}

/* -------------------------------- Страница -------------------------------- */

export interface AdminProductFormPageProps {
  mode: 'create' | 'edit';
}

export function AdminProductFormPage({ mode }: AdminProductFormPageProps) {
  const params = useParams<{ id: string }>();
  const productId = Number(params.id);
  const title = mode === 'edit' ? 'Редактирование товара' : 'Новый товар';

  if (mode === 'edit' && (!Number.isFinite(productId) || productId <= 0)) {
    return (
      <Page title={title} back backTo="/admin/products">
        <EmptyState
          icon="🔎"
          title="Товар не найден"
          text="Ссылка выглядит некорректной."
          action={<LinkButton to="/admin/products">К списку товаров</LinkButton>}
        />
      </Page>
    );
  }

  return (
    <Page title={title} back backTo="/admin/products">
      {mode === 'edit' ? (
        <EditProductLoader productId={productId} />
      ) : (
        <ProductForm product={null} />
      )}
    </Page>
  );
}
